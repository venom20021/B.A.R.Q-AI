"""
BARQ Agent Planner — decomposes high-level goals into actionable step plans.

Uses the LLM (Ollama via the existing client) to intelligently break down
a user's goal into a sequence of tool calls, then returns a structured plan
that the ``AgentExecutor`` can follow step-by-step.

Inspired by MARK XXXIX-OR's planner.py but adapted for BARQ's existing
toolset and async architecture.
"""

import json
import re

from utils.ollama_client import OllamaClient

from .skill_registry import get_skill_registry

# Dynamically generated from the SkillRegistry — reflects the actual
# set of registered skills/capabilities without hardcoding.
_PLANNER_SYSTEM_PROMPT_BASE = """You are the planning module of BARQ, an AI desktop assistant.
Your job: break any user goal into a sequence of steps using ONLY the tools listed below.

ABSOLUTE RULES:
- NEVER simulate or guess results — always plan to use real tools
- Max 5 steps. Use the minimum steps needed.
- Every step is independent — do not reference previous step results in parameters
- Use web_search for ANY information retrieval, research, or current data

{SKILL_LIST}

OUTPUT — return ONLY valid JSON, no markdown, no explanation:
{{
  "goal": "...",
  "steps": [
    {{
      "step": 1,
      "tool": "tool_name",
      "description": "what this step does",
      "parameters": {{}},
      "critical": true
    }}
  ]
}}
"""


def _get_planner_system_prompt() -> str:
    """Build the planner system prompt dynamically from the SkillRegistry.

    Replaces the old static ``PLANNER_SYSTEM_PROMPT`` with one that
    always reflects the current set of registered skills.
    """
    registry = get_skill_registry()
    skill_list = registry.to_planner_prompt()
    return _PLANNER_SYSTEM_PROMPT_BASE.format(SKILL_LIST=skill_list)


async def create_plan(goal: str, context: str = "") -> dict:
    """Break a user goal into a step-by-step plan using the LLM.

    Args:
        goal: The user's high-level goal (e.g. "research quantum computing and save to file").
        context: Optional additional context about the user or environment.

    Returns:
        A dict with ``goal`` and ``steps`` (list of step dicts).
        Each step has: step, tool, description, parameters, critical.
    """
    llm = OllamaClient()
    user_input = f"Goal: {goal}"
    if context:
        user_input += f"\n\nContext: {context}"

    system_prompt = _get_planner_system_prompt()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input},
    ]

    try:
        response = await llm.chat(messages)

        text = response.strip()
        # Strip markdown fences if present
        text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()

        plan = json.loads(text)

        if "steps" not in plan or not isinstance(plan["steps"], list):
            raise ValueError("Invalid plan structure — missing 'steps' array")

        print(f"[AgentPlanner] OK Created plan: {len(plan['steps'])} steps for '{goal[:60]}...'")
        for s in plan["steps"]:
            print(f"  Step {s['step']}: [{s['tool']}] {s['description'][:80]}")

        return plan

    except (json.JSONDecodeError, ValueError) as e:
        print(f"[AgentPlanner] WARN Plan creation failed: {e}")
        return _fallback_plan(goal)
    except Exception as e:
        print(f"[AgentPlanner] WARN Unexpected error: {e}")
        return _fallback_plan(goal)


def _fallback_plan(goal: str) -> dict:
    """Generate a simple fallback plan when LLM planning fails."""
    print("[AgentPlanner] FALLBACK Using fallback plan")
    return {
        "goal": goal,
        "steps": [
            {
                "step": 1,
                "tool": "web_search",
                "description": f"Search for: {goal}",
                "parameters": {"query": goal},
                "critical": True,
            }
        ],
    }


async def replan(
    goal: str,
    completed_steps: list[dict],
    failed_step: dict,
    error: str,
) -> dict:
    """Create a revised plan after a step has failed.

    Args:
        goal: Original user goal.
        completed_steps: Steps that completed successfully.
        failed_step: The step that failed.
        error: Error message from the failed step.

    Returns:
        A revised plan dict with remaining steps.
    """
    llm = OllamaClient()

    completed_summary = "\n".join(
        f"  - Step {s['step']} ({s['tool']}): DONE" for s in completed_steps
    )

    prompt = f"""Goal: {goal}

Already completed:
{completed_summary if completed_summary else '  (none)'}

Failed step: [{failed_step.get('tool')}] {failed_step.get('description')}
Error: {error[:300]}

Create a REVISED plan for the remaining work only. Do not repeat completed steps."""

    system_prompt = _get_planner_system_prompt()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]

    try:
        response = await llm.chat(messages)
        text = response.strip()
        text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
        plan = json.loads(text)

        print(f"[AgentPlanner] REVISED plan: {len(plan['steps'])} steps")
        return plan
    except Exception as e:
        print(f"[AgentPlanner] WARN Replan failed: {e}")
        return _fallback_plan(goal)
