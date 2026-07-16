"""
BARQ Skill Registry — plugin-based dynamic tool registration for the agent system.

Replaces the hardcoded ``tool_map`` dict in ``agent_executor.py``, the static
``PLANNER_SYSTEM_PROMPT`` in ``agent_planner.py``, and the ``_SKIPPABLE_TOOLS``
set in ``error_handler.py`` with a single, extensible registry.

Skills can be registered:
- Programmatically via ``SkillRegistry().register(skill)``
- Built-in tools are registered at startup via ``register_builtin_skills()``
- File-based skills can be loaded from JSON skill descriptors

Usage::

    registry = SkillRegistry()
    await registry.call("web_search", query="quantum computing")
    prompt = registry.to_planner_prompt()
    skiplist = registry.get_skiplist()
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# Type alias for an async callable: ``(**kwargs) -> str``
AsyncCallable = Callable[..., Awaitable[str]]


# ─── Skill Data Model ───────────────────────────────────────────────────────


@dataclass
class SkillParameter:
    """A single parameter accepted by a skill."""

    name: str
    type: str = "string"
    required: bool = False
    description: str = ""

    def to_planner_line(self) -> str:
        req = "(required)" if self.required else "(optional)"
        return f"  {self.name}: {self.type} {req} — {self.description}"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type,
            "required": self.required,
            "description": self.description,
        }


@dataclass
class Skill:
    """A registered skill that the agent can use.

    Attributes:
        name: Unique identifier (e.g. ``"web_search"``)
        description: Human-readable description of what the skill does.
        parameters: List of accepted parameters.
        handler: Optional async callable ``(**kwargs) -> str``.
            If ``None``, the registry dispatches via HTTP using stored metadata.
        critical: If True, the error handler will not skip this skill.
        category: Grouping category (e.g. ``"web"``, ``"system"``, ``"files"``).
        metadata: Arbitrary extra data (e.g. route info for HTTP dispatch).
    """

    name: str
    description: str = ""
    parameters: list[SkillParameter] = field(default_factory=list)
    handler: Optional[AsyncCallable] = None
    critical: bool = True
    category: str = "general"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_planner_entry(self) -> str:
        """Format this skill for inclusion in the planner's system prompt."""
        lines = [f"\n{self.name}"]
        if self.description:
            lines.append(f"  Description: {self.description}")
        for param in self.parameters:
            lines.append(param.to_planner_line())
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": [p.to_dict() for p in self.parameters],
            "has_handler": self.handler is not None,
            "critical": self.critical,
            "category": self.category,
            "metadata": self.metadata,
        }


# ─── Skill Registry ────────────────────────────────────────────────────────


class SkillRegistry:
    """Singleton registry for agent skills.

    Manages a dynamic collection of ``Skill`` objects that the agent planner
    and executor use instead of hardcoded maps.
    """

    _instance: Optional["SkillRegistry"] = None
    _skills: dict[str, Skill] = {}

    def __new__(cls) -> "SkillRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._skills = {}
        return cls._instance

    # ── Registration ──────────────────────────────────────────────────

    def register(self, skill: Skill) -> None:
        """Register a skill.

        Args:
            skill: The Skill to register.

        Raises:
            ValueError: If a skill with the same name already exists.
        """
        if skill.name in self._skills:
            raise ValueError(f"Skill '{skill.name}' is already registered")
        self._skills[skill.name] = skill

    def register_or_replace(self, skill: Skill) -> None:
        """Register a skill, replacing any existing one with the same name."""
        self._skills[skill.name] = skill

    def unregister(self, name: str) -> None:
        """Remove a skill by name.

        Args:
            name: The skill name to remove.

        Raises:
            KeyError: If the skill is not found.
        """
        del self._skills[name]

    # ── Query ─────────────────────────────────────────────────────────

    def get(self, name: str) -> Optional[Skill]:
        """Get a skill by name.

        Returns:
            The Skill, or None if not found.
        """
        return self._skills.get(name)

    def list(self, category: Optional[str] = None) -> list[Skill]:
        """List all registered skills, optionally filtered by category."""
        if category:
            return [s for s in self._skills.values() if s.category == category]
        return list(self._skills.values())

    def names(self) -> list[str]:
        """Return all registered skill names."""
        return list(self._skills.keys())

    def count(self) -> int:
        """Return the number of registered skills."""
        return len(self._skills)

    def get_skiplist(self) -> set[str]:
        """Return the set of non-critical skill names for the error handler.

        The error handler uses this to decide which skills can be safely
        skipped without replanning.
        """
        return {name for name, skill in self._skills.items() if not skill.critical}

    # ── Planner Integration ───────────────────────────────────────────

    def to_planner_prompt(self) -> str:
        """Generate the ``AVAILABLE TOOLS AND THEIR PARAMETERS`` section
        for the planner system prompt.

        Returns:
            A formatted string listing all registered skills with their
            parameters and descriptions, ready to be embedded in a prompt.
        """
        if not self._skills:
            return "\n(No tools available)"

        lines = ["AVAILABLE TOOLS AND THEIR PARAMETERS:"]
        for name in sorted(self._skills.keys()):
            skill = self._skills[name]
            lines.append(skill.to_planner_entry())
        return "\n".join(lines)

    # ── Execution ─────────────────────────────────────────────────────

    async def call(self, skill_name: str, **params: Any) -> str:
        """Execute a skill by name with the given parameters.

        If the skill has an explicit ``handler``, it is called directly.
        Otherwise, the registry dispatches via HTTP using the convention
        stored in ``metadata`` (``route_method``, ``route_path``, ``route_payload``).

        Args:
            skill_name: Skill name.
            **params: Parameters to pass to the skill.

        Returns:
            The result string from the skill.

        Raises:
            ValueError: If the skill is not found.
            RuntimeError: If execution fails.
        """
        skill = self.get(skill_name)
        if skill is None:
            raise ValueError(f"Unknown skill: {skill_name}")

        if skill.handler is not None:
            # Direct handler call
            try:
                result = await skill.handler(**params)
                return result
            except Exception as e:
                raise RuntimeError(f"Skill '{skill_name}' execution failed: {e}") from e

        # HTTP dispatch
        method = skill.metadata.get("route_method", "POST")
        path = skill.metadata.get("route_path", "")
        payload_template = skill.metadata.get("route_payload", {})

        # Build payload from template + params
        payload = {}
        for key, default in payload_template.items():
            if default == "" or default is None:
                # Use param value if provided, else empty/None
                payload[key] = params.get(key, default if default is None else "")
            else:
                payload[key] = params.get(key, default)

        import httpx

        from config import get_settings

        settings = get_settings()
        url = f"http://{settings.host}:{settings.port}{path}"

        try:
            # Use a client per call (no shared state issues)
            async with httpx.AsyncClient(timeout=30.0) as client:
                if method == "GET":
                    resp = await client.get(url, params=payload, timeout=30.0)
                else:
                    resp = await client.post(url, json=payload, timeout=30.0)

                if resp.status_code >= 400:
                    error_detail = ""
                    try:
                        error_detail = resp.json().get("detail", resp.text)
                    except Exception:
                        error_detail = resp.text[:200]
                    raise RuntimeError(
                        f"Skill '{skill_name}' returned HTTP {resp.status_code}: {error_detail}"
                    )

                data = resp.json()
                if isinstance(data, dict):
                    for key in ("output", "text", "result", "message", "content", "status"):
                        if key in data and data[key]:
                            return str(data[key])
                return str(data)[:200]

        except httpx.RequestError as e:
            raise RuntimeError(f"Skill '{skill_name}' network error: {e}")

    # ── File-based Discovery ────────────────────────────────────────

    def discover(self, directory: str | Path) -> int:
        """Scan a directory for skill descriptor files and register them.

        Looks for ``.skill.json`` files in the given directory (non-recursive).
        Each file should have the structure::

            {
                "name": "my_skill",
                "description": "Does something useful",
                "parameters": [
                    {"name": "query", "type": "string", "required": true, "description": "..."}
                ],
                "route_method": "POST",
                "route_path": "/custom/endpoint",
                "route_payload": {"query": ""},
                "critical": true,
                "category": "custom"
            }

        Skills registered this way use HTTP dispatch (no handler).

        Args:
            directory: Path to scan.

        Returns:
            Number of skills registered.
        """
        dir_path = Path(directory)
        count = 0
        for f in sorted(dir_path.glob("*.skill.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                params = [
                    SkillParameter(
                        name=p["name"],
                        type=p.get("type", "string"),
                        required=p.get("required", False),
                        description=p.get("description", ""),
                    )
                    for p in data.get("parameters", [])
                ]
                skill = Skill(
                    name=data["name"],
                    description=data.get("description", ""),
                    parameters=params,
                    handler=None,
                    critical=data.get("critical", True),
                    category=data.get("category", "custom"),
                    metadata={
                        "route_method": data.get("route_method", "POST"),
                        "route_path": data.get("route_path", ""),
                        "route_payload": data.get("route_payload", {}),
                    },
                )
                self.register_or_replace(skill)
                count += 1
            except Exception as e:
                print(f"[SkillRegistry] SKIP Failed to load {f}: {e}")

        return count

    # ── Serialization ───────────────────────────────────────────────

    def summary(self) -> list[dict]:
        """Return a summary of all registered skills (handler-safe)."""
        return [s.to_dict() for s in self._skills.values()]

    def clear(self) -> None:
        """Remove all registered skills (useful for testing)."""
        self._skills.clear()


# ─── Singleton Accessor ───────────────────────────────────────────────────

_registry: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    """Get or create the global SkillRegistry singleton."""
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
    return _registry


# ─── Built-in Skill Registration ──────────────────────────────────────────


def register_builtin_skills(registry: Optional[SkillRegistry] = None) -> SkillRegistry:
    """Register all built-in BARQ agent tools as skills.

    These are the tools previously hardcoded in ``agent_executor._call_tool``'s
    ``tool_map`` dict.  They are dispatched via HTTP to BARQ's own FastAPI routes.

    Args:
        registry: An optional registry to register into.  If ``None``, uses
            the global singleton.

    Returns:
        The registry (for chaining).
    """
    reg = registry or get_skill_registry()

    builtins: list[Skill] = [
        Skill(
            name="web_search",
            description="Search the web for information on any topic. Use clear, focused keywords.",
            parameters=[
                SkillParameter("query", "string", True, "Clear, focused search query"),
            ],
            critical=True,
            category="web",
            metadata={"route_method": "POST", "route_path": "/web/browse/search", "route_payload": {"query": ""}},
        ),
        Skill(
            name="launch_app",
            description="Launch or open a desktop application by its name.",
            parameters=[
                SkillParameter("app_name", "string", True, "Name of the application to launch"),
            ],
            critical=True,
            category="system",
            metadata={"route_method": "POST", "route_path": "/system/launch-app", "route_payload": {"app_name": ""}},
        ),
        Skill(
            name="system_command",
            description="Run a terminal command on the local machine. Use carefully.",
            parameters=[
                SkillParameter("command", "string", True, "The terminal command to run"),
                SkillParameter("cwd", "string", False, "Working directory for the command"),
            ],
            critical=True,
            category="system",
            metadata={"route_method": "POST", "route_path": "/system/terminal/run", "route_payload": {"command": "", "cwd": None}},
        ),
        Skill(
            name="create_file",
            description="Create a new file with the given content at the specified path.",
            parameters=[
                SkillParameter("path", "string", True, "File path to create"),
                SkillParameter("content", "string", False, "File content"),
            ],
            critical=True,
            category="files",
            metadata={"route_method": "POST", "route_path": "/system/file/write", "route_payload": {"path": "", "content": ""}},
        ),
        Skill(
            name="read_file",
            description="Read the contents of a file at the specified path.",
            parameters=[
                SkillParameter("path", "string", True, "File path to read"),
            ],
            critical=False,
            category="files",
            metadata={"route_method": "POST", "route_path": "/system/file/read", "route_payload": {"path": ""}},
        ),
        Skill(
            name="get_weather",
            description="Get the current weather for a given city.",
            parameters=[
                SkillParameter("city", "string", True, "City name (e.g. 'London', 'Tokyo')"),
            ],
            critical=False,
            category="web",
            metadata={"route_method": "GET", "route_path": "/web/weather", "route_payload": {"city": "London"}},
        ),
        Skill(
            name="browse_url",
            description="Visit a URL and extract its readable content.",
            parameters=[
                SkillParameter("url", "string", True, "The full URL to visit"),
            ],
            critical=False,
            category="web",
            metadata={"route_method": "POST", "route_path": "/web/browse", "route_payload": {"url": ""}},
        ),
        Skill(
            name="send_message",
            description="Send a message to the user via a notification platform.",
            parameters=[
                SkillParameter("receiver", "string", True, "Recipient identifier"),
                SkillParameter("message", "string", True, "Message content"),
                SkillParameter("platform", "string", False, "Platform: telegram (default), email, desktop"),
            ],
            critical=False,
            category="communications",
            metadata={"route_method": "POST", "route_path": "/notifications/send", "route_payload": {"receiver": "", "message": "", "platform": "telegram"}},
        ),
        Skill(
            name="check_trends",
            description="Check current trending topics on social media.",
            parameters=[
                SkillParameter("topic", "string", False, "Optional topic to check trends for"),
            ],
            critical=False,
            category="social",
            metadata={"route_method": "GET", "route_path": "/social/trends", "route_payload": {"topic": ""}},
        ),
    ]

    for skill in builtins:
        try:
            reg.register(skill)
        except ValueError:
            # Skill already registered (e.g. from a previous call)
            pass

    print(f"[SkillRegistry] Registered {len(builtins)} built-in skills")
    return reg


# Auto-register built-in skills when this module is imported.
# This ensures skills are always available, even when TestClient or
# direct imports are used without triggering the application lifespan.
register_builtin_skills()


# ─── Dynamic Skill Registration Helper ───────────────────────────────────


def create_skill_from_handler(
    name: str,
    handler: AsyncCallable,
    description: str = "",
    parameters: Optional[list[SkillParameter]] = None,
    critical: bool = True,
    category: str = "custom",
) -> Skill:
    """Create a Skill from a Python async handler function.

    This is the primary way to add custom plugin skills.  The handler
    receives ``**kwargs`` matching the declared parameters and must
    return a string result.

    Args:
        name: Unique skill name.
        handler: Async callable ``(**kwargs) -> str``.
        description: Human-readable description.
        parameters: List of accepted parameters.
        critical: Whether this skill is critical (non-skippable).
        category: Grouping category.

    Returns:
        A Skill ready to be registered.
    """
    return Skill(
        name=name,
        description=description,
        parameters=parameters or [],
        handler=handler,
        critical=critical,
        category=category,
        metadata={"source": "plugin"},
    )
