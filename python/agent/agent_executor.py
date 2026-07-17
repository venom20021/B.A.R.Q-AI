"""
BARQ Agent Executor — executes multi-step plans with intelligent error recovery.

Takes a plan from ``AgentPlanner`` and runs each step sequentially.
If a step fails, the ``AgentErrorHandler`` analyzes the error and decides
whether to retry, skip, replan, or abort.  Supports cancellation via
an optional ``asyncio.Event``.

Inspired by MARK XXXIX-OR's executor.py but adapted for BARQ's async
FastAPI backend and existing tool routes.
"""

import asyncio
from typing import Any, Callable, Optional

from .agent_planner import create_plan, replan
from .error_handler import ErrorDecision, analyze_error
from .skill_registry import get_skill_registry


class AgentExecutor:
    """Executes multi-step agent plans with intelligent error recovery.

    Usage::

        executor = AgentExecutor()
        result = await executor.execute(
            goal="Research quantum computing and save to a file",
            speak=some_speak_function,
        )
    """

    MAX_REPLAN_ATTEMPTS = 2

    def __init__(self, http_client: Optional[Any] = None):
        self._http_client = http_client  # optional httpx.AsyncClient for API calls
        self._skill_registry = get_skill_registry()

    async def execute(
        self,
        goal: str,
        speak: Optional[Callable] = None,
        cancel_flag: Optional[asyncio.Event] = None,
    ) -> str:
        """Execute a goal by planning, running steps, and recovering from errors.

        Args:
            goal: The user's high-level goal.
            speak: Optional async callable to speak status updates.
            cancel_flag: Optional event to cancel execution.

        Returns:
            A summary string of what was accomplished.
        """
        print(f"\n[AgentExecutor] >> Goal: {goal}")

        replan_attempts = 0
        completed_steps: list[dict] = []
        step_results: dict[str, str] = {}
        plan = await create_plan(goal)

        while True:
            steps = plan.get("steps", [])

            if not steps:
                msg = "I couldn't create a valid plan for this task."
                if speak:
                    await speak(msg)
                return msg

            success = True
            failed_step = None
            failed_error = ""

            for step in steps:
                if cancel_flag and cancel_flag.is_set():
                    if speak:
                        await speak("Task cancelled.")
                    return "Task cancelled."

                step_num = step.get("step", "?")
                tool = step.get("tool", "web_search")
                desc = step.get("description", "")
                params = step.get("parameters", {})

                # Inject context from previous step results
                params = await self._inject_context(params, tool, step_results, goal)

                print(f"\n[AgentExecutor] >> Step {step_num}: [{tool}] {desc}")

                attempt = 1
                step_ok = False

                while attempt <= 3:
                    if cancel_flag and cancel_flag.is_set():
                        break
                    try:
                        result = await self._call_tool(tool, params)
                        step_results[str(step_num)] = result
                        completed_steps.append(step)
                        print(f"[AgentExecutor] OK Step {step_num} done: {str(result)[:100]}")
                        step_ok = True
                        break

                    except Exception as e:
                        error_msg = str(e)
                        print(f"[AgentExecutor] FAIL Step {step_num} attempt {attempt} failed: {error_msg}")

                        recovery = analyze_error(step, error_msg, attempt=attempt)
                        decision = recovery["decision"]
                        user_msg = recovery.get("user_message", "")

                        if speak and user_msg:
                            await speak(user_msg)

                        if decision == ErrorDecision.RETRY:
                            attempt += 1
                            await asyncio.sleep(2)
                            continue

                        elif decision == ErrorDecision.SKIP:
                            print(f"[AgentExecutor] SKIP Step {step_num}")
                            completed_steps.append(step)
                            step_ok = True
                            break

                        elif decision == ErrorDecision.ABORT:
                            msg = f"Task aborted. {recovery.get('reason', '')}"
                            if speak:
                                await speak(msg)
                            return msg

                        else:  # REPLAN
                            fix_suggestion = recovery.get("fix_suggestion", "")
                            if fix_suggestion:
                                try:
                                    print(f"[AgentExecutor] FIX Trying: {fix_suggestion}")
                                    res = await self._call_tool(tool, {**params, "description": fix_suggestion})
                                    step_results[str(step_num)] = res
                                    completed_steps.append(step)
                                    step_ok = True
                                    break
                                except Exception as fix_err:
                                    print(f"[AgentExecutor] WARN Fix failed: {fix_err}")

                            failed_step = step
                            failed_error = error_msg
                            success = False
                            break

                if not step_ok and not failed_step:
                    failed_step = step
                    failed_error = "Max retries exceeded"
                    success = False

                if not success:
                    break

            if success:
                return await self._summarize(goal, completed_steps, step_results)

            if replan_attempts >= self.MAX_REPLAN_ATTEMPTS:
                msg = f"Task failed after {replan_attempts} replan attempts."
                if speak:
                    await speak(msg)
                return msg

            if speak:
                await speak("Adjusting my approach.")

            replan_attempts += 1
            plan = await replan(goal, completed_steps, failed_step, failed_error)

    async def _call_tool(self, tool: str, parameters: dict) -> str:
        """Execute a single tool call by dispatching to the SkillRegistry.

        Replaces the old hardcoded ``tool_map`` with the dynamic
        ``SkillRegistry``, enabling plugin-based skill discovery
        and execution.

        Args:
            tool: Tool name (e.g. 'web_search', 'launch_app', 'system_command').
            parameters: Dict of parameters for the tool.

        Returns:
            Result string from the tool.

        Raises:
            ValueError: If the tool is not found in the registry.
            RuntimeError: If execution fails.
        """
        return await self._skill_registry.call(tool, **parameters)

    async def _inject_context(
        self,
        params: dict,
        tool: str,
        step_results: dict[str, str],
        goal: str = "",
    ) -> dict:
        """Inject context from previous step results into tool parameters.

        For example, if step 1 searched the web and step 2 needs to save
        the result, this injects the search result into the file content.
        """
        if not step_results:
            return params

        params = dict(params)

        if tool == "create_file":
            # Inject content from previous step results
            if not params.get("content"):
                all_results = [
                    v for v in step_results.values()
                    if v and len(v) > 50 and v not in ("Done.", "Completed.")
                ]
                if all_results:
                    params["content"] = "\n\n---\n\n".join(all_results)

            # Inject a proper filename if path is empty / "." / directory
            path_val = params.get("path", "")
            if not path_val or path_val.strip() in (".", "", "./", ".."):
                # Derive a filename from the goal
                goal_short = "".join(c for c in goal if c.isalnum() or c in " _-").strip()[:30]
                params["path"] = f"./{goal_short.replace(' ', '_').lower() or 'barq_output'}.txt"

        return params

    async def _summarize(self, goal: str, completed_steps: list[dict], step_results: Optional[dict[str, str]] = None) -> str:
        """Generate a natural summary of what was accomplished.

        If the LLM is unavailable, uses the ``respond`` step's output
        (if present) as a fallback instead of a generic "Completed N steps"
        message.
        """
        from utils.ollama_client import OllamaClient

        steps_str = "\n".join(
            f"- {s.get('description', '')}" for s in completed_steps
        )

        prompt = (
            f'User goal: "{goal}"\n'
            f"Completed steps:\n{steps_str}\n\n"
            "Write a single natural sentence summarizing what was accomplished. "
            "Be direct and positive."
        )

        messages = [
            {"role": "system", "content": "You summarize completed tasks concisely."},
            {"role": "user", "content": prompt},
        ]

        try:
            llm = OllamaClient()
            summary = await llm.chat(messages)
            return summary.strip()
        except Exception:
            # LLM unavailable — use the last meaningful step result as fallback
            if step_results:
                # Get the last step result (usually the respond step)
                last_key = max(step_results.keys(), key=lambda k: int(k) if k.isdigit() else 0)
                last_result = step_results.get(last_key, "")
                if last_result and len(last_result) > 5 and "I'm here" not in last_result:
                    return last_result

                # If that didn't work, try any non-trivial result from any step
                for key in sorted(step_results.keys(), key=lambda k: int(k) if k.isdigit() else 0, reverse=True):
                    val = step_results[key]
                    if val and len(val) > 20 and "Completed" not in val and "here to help" not in val:
                        return val[:500]

            return f"Completed {len(completed_steps)} steps for: {goal[:60]}."
