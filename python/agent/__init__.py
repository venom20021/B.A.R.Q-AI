"""
BARQ Agent System — Autonomous multi-step task planning & execution.

Inspired by the MARK XXXIX-OR agent architecture, this module enables
BARQ to decompose complex goals into step-by-step plans, execute them
with intelligent error recovery, and queue tasks for background processing.

Components:
    - ``AgentPlanner``: Breaks goals into steps using available tools.
    - ``AgentExecutor``: Runs step plans with retry/error recovery logic.
    - ``AgentTaskQueue``: Priority-based background task queue.
    - ``AgentErrorHandler``: Analyzes failures and decides recovery strategy.
    - ``SkillRegistry``: Plugin-based dynamic tool registry replacing hardcoded tool_map.
"""

from .agent_executor import AgentExecutor
from .agent_planner import create_plan, replan
from .error_handler import ErrorDecision, analyze_error
from .skill_registry import (
    Skill,
    SkillParameter,
    SkillRegistry,
    create_skill_from_handler,
    get_skill_registry,
    register_builtin_skills,
)
from .task_queue import AgentTaskQueue, TaskPriority, TaskStatus

# Register agentic workflow skills (W1-W7) as soon as the agent package is
# imported — not only via main.py's lifespan — so the planner always sees them
# regardless of the entrypoint. Idempotent.
from .agentic_skills import register_agentic_skills as _register_agentic_skills

_register_agentic_skills()

__all__ = [
    "AgentExecutor",
    "AgentPlanner",
    "AgentTaskQueue",
    "TaskPriority",
    "TaskStatus",
    "ErrorDecision",
    "Skill",
    "SkillParameter",
    "SkillRegistry",
    "get_skill_registry",
    "register_builtin_skills",
    "create_skill_from_handler",
    "create_plan",
    "replan",
    "analyze_error",
    "generate_fix",
]
