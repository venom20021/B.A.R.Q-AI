"""
BARQ Workflow Runtime — composable agentic workflow engine.

Implements the Prompt-Chaining, Orchestrator-Workers (parallel delegation),
and Plan-Act-Reflect patterns on top of the existing SkillRegistry:

- Workflows are JSON definitions: ordered steps, optional parallel groups,
  per-step success/failure routing, and ``${step.<id>}`` context injection
  from prior step results.
- Steps dispatch through ``SkillRegistry.call()`` so every workflow reuses
  the existing tool skills, analytics, and error handling.
- Runs are checkpointed (W2) so long workflows survive restarts.

Example workflow (research → save):
    {
        "name": "evening_research",
        "description": "Deep research a topic and save the report to a file",
        "steps": [
            {"id": "research", "skill": "deep_research", "params": {"topic": "${context.topic}", "depth": "standard"}},
            {"id": "save", "skill": "create_file", "params": {"path": "./research_output.txt", "content": "${step.research}"}}
        ]
    }
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .skill_registry import get_skill_registry


# ─── Data model ────────────────────────────────────────────────────────────


@dataclass
class WorkflowStep:
    """A single step in a workflow definition."""

    id: str
    skill: str
    params: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    next_on_success: Optional[str] = None   # default: next step in list
    next_on_failure: Optional[str] = None   # default: fail the workflow
    parallel_with: list[str] = field(default_factory=list)  # sibling step ids
    critical: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowStep":
        return cls(
            id=str(data.get("id", "")),
            skill=str(data.get("skill", "")),
            params=data.get("params", {}) or {},
            description=data.get("description", ""),
            next_on_success=data.get("next_on_success"),
            next_on_failure=data.get("next_on_failure"),
            parallel_with=data.get("parallel_with", []) or [],
            critical=bool(data.get("critical", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "skill": self.skill,
            "params": self.params,
            "description": self.description,
            "next_on_success": self.next_on_success,
            "next_on_failure": self.next_on_failure,
            "parallel_with": self.parallel_with,
            "critical": self.critical,
        }


@dataclass
class Workflow:
    """A named, reusable workflow definition."""

    name: str
    description: str = ""
    steps: list[WorkflowStep] = field(default_factory=list)
    trigger: str = "manual"          # manual | cron
    cron: Optional[str] = None       # cron expression when trigger == 'cron'
    timeout_seconds: int = 600

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Workflow":
        return cls(
            name=str(data.get("name", "")),
            description=data.get("description", ""),
            steps=[WorkflowStep.from_dict(s) for s in data.get("steps", [])],
            trigger=data.get("trigger", "manual"),
            cron=data.get("cron"),
            timeout_seconds=int(data.get("timeout_seconds", 600)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "trigger": self.trigger,
            "cron": self.cron,
            "timeout_seconds": self.timeout_seconds,
        }


# ─── Runtime ───────────────────────────────────────────────────────────────


class WorkflowRuntime:
    """Executes workflow definitions by dispatching steps to the SkillRegistry."""

    def __init__(self):
        self._workflows: dict[str, Workflow] = {}
        self._runs: dict[str, dict[str, Any]] = {}

    # ── Workflow registry ────────────────────────────────────────────

    def register(self, workflow: Workflow) -> None:
        self._workflows[workflow.name] = workflow

    def register_or_replace(self, workflow: Workflow) -> None:
        self._workflows[workflow.name] = workflow

    def get(self, name: str) -> Optional[Workflow]:
        return self._workflows.get(name)

    def list_workflows(self) -> list[dict[str, Any]]:
        return [w.to_dict() for w in self._workflows.values()]

    def remove(self, name: str) -> bool:
        return self._workflows.pop(name, None) is not None

    def load_from_dict(self, data: dict[str, Any]) -> Workflow:
        """Register a workflow from a JSON dict and return it."""
        wf = Workflow.from_dict(data)
        self.register_or_replace(wf)
        return wf

    # ── Execution ────────────────────────────────────────────────────

    async def run(
        self,
        name: str,
        context: Optional[dict[str, Any]] = None,
        run_id: Optional[str] = None,
        progress_cb: Optional[Callable] = None,
        checkpoint: bool = True,
    ) -> dict[str, Any]:
        """Execute a workflow by name.

        Args:
            name: Registered workflow name.
            context: User/environment context (accessible as ${context.<key>}).
            run_id: Optional run identifier (auto-generated).
            progress_cb: Optional async callable(step_id, status, result).
            checkpoint: Whether to persist run progress (default True).

        Returns:
            dict with run_id, status, results, error (if any).
        """
        workflow = self.get(name)
        if workflow is None:
            raise ValueError(f"Unknown workflow: {name}")

        run_id = run_id or f"workflow:{uuid.uuid4().hex[:8]}"
        run_state: dict[str, Any] = {
            "run_id": run_id,
            "workflow": name,
            "status": "running",
            "started_at": time.time(),
            "step_results": {},
            "results": [],
            "error": "",
        }
        self._runs[run_id] = run_state
        context = context or {}

        # Resume support: previous run state (if any) is reloaded below.
        from .checkpoint_store import get_checkpoint_store
        completed_ids: set[str] = set()
        if checkpoint:
            try:
                prev = await get_checkpoint_store().load(run_id)
                if prev:
                    run_state["step_results"] = prev.get("step_results", {})
                    run_state["results"] = prev.get("results", [])
                    completed_ids = {r.get("id") for r in run_state["results"] if r.get("status") == "completed"}
            except Exception as e:
                print(f"[WorkflowRuntime] Checkpoint restore skipped: {e}")

        try:
            steps = list(workflow.steps)
            index = 0
            # Loop guard: if routing (next_on_failure / next_on_success) lands
            # on a step more than MAX_ROUTE_TIMES, fail instead of looping forever.
            route_counts: dict[str, int] = {}
            MAX_ROUTE_TIMES = 3

            def _guard_route(step_id: str, steps_list: list[WorkflowStep]) -> Optional[int]:
                """Increment route count and return the step index, or None if looped."""
                route_counts[step_id] = route_counts.get(step_id, 0) + 1
                if route_counts[step_id] > MAX_ROUTE_TIMES:
                    return None
                return WorkflowRuntime._find_step_index(steps_list, step_id, index)

            while index < len(steps):
                step = steps[index]

                # ── Build parallel group (Orchestrator-Workers) ──
                parallel_ids = [s for s in step.parallel_with if s != step.id]
                group = [step]
                group_ids = {step.id}
                if parallel_ids:
                    remaining = {s.id: s for s in steps[index + 1:]}
                    for pid in parallel_ids:
                        if pid in remaining and pid not in group_ids:
                            group.append(remaining[pid])
                            group_ids.add(pid)

                # Skip entire group if already completed
                if group_ids.issubset(completed_ids):
                    index += len(group)
                    continue

                # ── Execute step or parallel group (Orchestrator-Workers) ──
                group_results: list[dict[str, Any]]
                if len(group) == 1:
                    group_results = [
                        await self._run_step(step, context, run_state, checkpoint, progress_cb)
                    ]
                else:
                    raw_results = await asyncio.gather(
                        *[self._run_step(s, context, run_state, checkpoint, progress_cb) for s in group],
                        return_exceptions=True,
                    )
                    group_results = [
                        r if isinstance(r, dict) else {"status": "failed", "error": str(r)}
                        for r in raw_results
                    ]

                # ── Check routing / failures ──
                failed = [r for r in group_results if r.get("status") != "completed"]
                if failed:
                    first_failed = next(
                        (s for s in group if s.id in {f.get("id") for f in failed}),
                        group[0],
                    )
                    if step.next_on_failure:
                        # Route to the failure-continuation step
                        nxt = _guard_route(step.next_on_failure, steps)
                        if nxt is None:
                            run_state["status"] = "failed"
                            run_state["error"] = (
                                f"Workflow loop or unknown route on failure: "
                                f"'{step.next_on_failure}' (visited {route_counts.get(step.next_on_failure, 0)}x)"
                            )
                            break
                        index = nxt
                        continue
                    if step.critical or any(s.critical for s in group):
                        run_state["status"] = "failed"
                        run_state["error"] = str(failed[0].get("error", "Step failed"))
                        break
                    # Non-critical failure → continue to next step
                    index += len(group)
                    continue

                # Success → follow next_on_success routing or proceed
                if step.next_on_success:
                    nxt = _guard_route(step.next_on_success, steps)
                    if nxt is None:
                        run_state["status"] = "failed"
                        run_state["error"] = (
                            f"Workflow loop detected on success route to "
                            f"'{step.next_on_success}'"
                        )
                        break
                    index = nxt
                    continue
                index += len(group)

            if run_state["status"] == "running":
                run_state["status"] = "completed"
            if checkpoint:
                try:
                    await get_checkpoint_store().mark_complete(run_id)
                except Exception:
                    pass

        except asyncio.CancelledError:
            run_state["status"] = "cancelled"
            raise
        except Exception as e:
            run_state["status"] = "failed"
            run_state["error"] = str(e)
            print(f"[WorkflowRuntime] FAIL {name}: {e}")

        run_state["elapsed_seconds"] = round(time.time() - run_state["started_at"], 1)
        return run_state

    # ── Internals ────────────────────────────────────────────────────

    async def _run_step(
        self,
        step: WorkflowStep,
        context: dict[str, Any],
        run_state: dict[str, Any],
        checkpoint: bool,
        progress_cb: Optional[Callable] = None,
    ) -> dict[str, Any]:
        """Execute a single workflow step via the SkillRegistry.

        Fires ``progress_cb(step_id, status, entry)`` for ``running``,
        ``completed``, and ``failed`` transitions so live streams get
        per-step updates as they happen.
        """
        params = self._resolve_params(step.params, context, run_state.get("step_results", {}))
        entry = {"id": step.id, "skill": step.skill, "status": "running"}
        run_state["results"].append(entry)
        if progress_cb:
            try:
                await progress_cb(step.id, "running", entry)
            except Exception:
                pass

        try:
            registry = get_skill_registry()
            result = await registry.call(step.skill, **params)
            result_text = result if isinstance(result, str) else str(result)
            run_state["step_results"][step.id] = result_text
            entry["status"] = "completed"
            entry["result_preview"] = result_text[:200]
            if progress_cb:
                try:
                    await progress_cb(step.id, "completed", entry)
                except Exception:
                    pass

            if checkpoint:
                try:
                    from .checkpoint_store import get_checkpoint_store
                    await get_checkpoint_store().save(
                        run_state["run_id"],
                        {
                            "workflow": run_state["workflow"],
                            "step_results": run_state["step_results"],
                            "results": run_state["results"],
                        },
                        agent_type="workflow",
                    )
                except Exception:
                    pass
            return entry

        except Exception as e:
            entry["status"] = "failed"
            entry["error"] = str(e)
            if progress_cb:
                try:
                    await progress_cb(step.id, "failed", entry)
                except Exception:
                    pass
            print(f"[WorkflowRuntime] STEP FAIL [{step.id}] {step.skill}: {e}")
            return entry

    @staticmethod
    def _resolve_params(
        params: dict[str, Any],
        context: dict[str, Any],
        step_results: dict[str, Any],
    ) -> dict[str, Any]:
        """Resolve ${context.<key>} and ${step.<id>} placeholders in params."""
        resolved: dict[str, Any] = {}
        for key, value in params.items():
            if isinstance(value, str):
                resolved[key] = WorkflowRuntime._resolve_string(value, context, step_results)
            elif isinstance(value, dict):
                resolved[key] = WorkflowRuntime._resolve_params(value, context, step_results)
            elif isinstance(value, list):
                resolved[key] = [
                    WorkflowRuntime._resolve_string(v, context, step_results) if isinstance(v, str) else v
                    for v in value
                ]
            else:
                resolved[key] = value
        return resolved

    @staticmethod
    def _resolve_string(template: str, context: dict[str, Any], step_results: dict[str, Any]) -> str:
        def repl(match: re.Match) -> str:
            token = match.group(1).strip()
            if token.startswith("step."):
                return str(step_results.get(token[5:], ""))
            if token.startswith("context."):
                return str(context.get(token[8:], ""))
            return match.group(0)

        return re.sub(r"\$\{([^}]+)\}", repl, template)

    @staticmethod
    def _find_step_index(steps: list[WorkflowStep], step_id: str, current: int) -> Optional[int]:
        for i, s in enumerate(steps):
            if s.id == step_id and i != current:
                return i
        return None

    # ── Run status ───────────────────────────────────────────────────

    def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        run = self._runs.get(run_id)
        return dict(run) if run else None

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        return [
            {k: v for k, v in r.items() if k != "results"}
            for r in list(self._runs.values())[-limit:]
        ]


# ─── Singleton + seed workflows ───────────────────────────────────────────

_runtime: Optional[WorkflowRuntime] = None


def get_workflow_runtime() -> WorkflowRuntime:
    """Get or create the global WorkflowRuntime singleton."""
    global _runtime
    if _runtime is None:
        _runtime = WorkflowRuntime()
        _seed_default_workflows(_runtime)
    return _runtime


def _seed_default_workflows(runtime: WorkflowRuntime) -> None:
    """Register a small set of example workflows that compose existing skills.

    These demonstrate Prompt-Chaining (research → save) and
    Orchestrator-Workers (parallel weather + trends) patterns.
    """
    runtime.register_or_replace(Workflow(
        name="evening_research",
        description="Deep research a topic and save the report to a file (chained steps).",
        steps=[
            WorkflowStep(
                id="research",
                skill="deep_research",
                params={"topic": "${context.topic}", "depth": "standard"},
                description="Research the topic",
            ),
            WorkflowStep(
                id="save",
                skill="create_file",
                params={"path": "${context.output_path}", "content": "${step.research}"},
                description="Save the report to a file",
            ),
        ],
    ))
    runtime.register_or_replace(Workflow(
        name="weather_and_trends",
        description="Fetch weather and trending topics in parallel, then summarize.",
        steps=[
            WorkflowStep(
                id="weather",
                skill="get_weather",
                params={"city": "${context.city}"},
                description="Get the weather",
            ),
            WorkflowStep(
                id="trends",
                skill="check_trends",
                params={"topic": "${context.topic}"},
                description="Check trends",
                parallel_with=["weather"],
            ),
            WorkflowStep(
                id="summary",
                skill="respond",
                params={"message": "Weather: ${step.weather}\nTrends: ${step.trends}"},
                description="Summarize both results",
            ),
        ],
    ))


async def run_workflow_skill(
    name: str,
    context: Optional[dict[str, Any]] = None,
    **kwargs: Any,
) -> str:
    """Skill handler: run a registered workflow by name (used by the planner)."""
    context = context or {}
    if kwargs:
        context.update(kwargs)
    runtime = get_workflow_runtime()
    try:
        result = await runtime.run(name, context=context, checkpoint=False)
    except ValueError as e:
        return f"Workflow not found: {e}"
    if result["status"] == "failed":
        return f"Workflow '{name}' failed: {result.get('error', 'unknown error')}"
    completed = sum(1 for r in result.get("results", []) if r.get("status") == "completed")
    return (
        f"Workflow '{name}' {result['status']} — {completed} step(s) completed "
        f"in {result.get('elapsed_seconds', 0)}s."
    )
