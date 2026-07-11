"""Tests for the BARQ Skill Registry.

Tests the plugin-based skill registry that replaces the hardcoded tool_map.
Covers: registration, querying, skiplist, planner prompt generation,
built-in skill registration, file-based discovery, and the create_skill_from_handler helper.
"""

import pytest

from agent.skill_registry import (
    Skill,
    SkillParameter,
    SkillRegistry,
    create_skill_from_handler,
    get_skill_registry,
    register_builtin_skills,
)

# ─── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def clean_registry():
    """Return a fresh SkillRegistry with no skills registered.

    The singleton is cleared before each test so tests don't leak state.
    """
    reg = get_skill_registry()
    reg.clear()
    return reg


# ─── Skill Dataclass ──────────────────────────────────────────────────────


class TestSkill:
    """Tests for the Skill dataclass."""

    def test_minimal_skill(self):
        skill = Skill(name="test_tool")
        assert skill.name == "test_tool"
        assert skill.description == ""
        assert skill.parameters == []
        assert skill.handler is None
        assert skill.critical is True
        assert skill.category == "general"
        assert skill.metadata == {}

    def test_full_skill(self):
        params = [SkillParameter("query", "string", True, "The query")]
        skill = Skill(
            name="search",
            description="Searches the web",
            parameters=params,
            critical=False,
            category="web",
            metadata={"route_method": "GET"},
        )
        assert skill.name == "search"
        assert len(skill.parameters) == 1
        assert skill.parameters[0].name == "query"
        assert skill.critical is False
        assert skill.category == "web"

    def test_to_planner_entry_with_params(self):
        params = [
            SkillParameter("query", "string", True, "Search query"),
            SkillParameter("limit", "integer", False, "Max results"),
        ]
        skill = Skill(name="web_search", description="Search tool", parameters=params)
        entry = skill.to_planner_entry()
        assert "web_search" in entry
        assert "query" in entry
        assert "(required)" in entry
        assert "limit" in entry
        assert "(optional)" in entry
        assert "Search tool" in entry

    def test_to_planner_entry_no_params(self):
        skill = Skill(name="simple_tool")
        entry = skill.to_planner_entry()
        assert entry == "\nsimple_tool"

    def test_to_dict_structure(self):
        skill = Skill(name="test", description="A test", critical=False, category="web")
        d = skill.to_dict()
        assert d["name"] == "test"
        assert d["description"] == "A test"
        assert d["critical"] is False
        assert d["category"] == "web"
        assert d["has_handler"] is False
        assert "parameters" in d


# ─── SkillParameter ────────────────────────────────────────────────────────


class TestSkillParameter:
    """Tests for the SkillParameter dataclass."""

    def test_to_planner_line_required(self):
        p = SkillParameter("query", "string", True, "The search query")
        line = p.to_planner_line()
        assert "query" in line
        assert "string" in line
        assert "(required)" in line
        assert "search query" in line

    def test_to_planner_line_optional(self):
        p = SkillParameter("limit", "integer", False, "Max results")
        line = p.to_planner_line()
        assert "(optional)" in line

    def test_to_dict(self):
        p = SkillParameter("name", "string", True, "Name field")
        d = p.to_dict()
        assert d["name"] == "name"
        assert d["type"] == "string"
        assert d["required"] is True


# ─── SkillRegistry ─────────────────────────────────────────────────────────


class TestSkillRegistry:
    """Tests for the SkillRegistry singleton."""

    def test_register_and_get(self, clean_registry):
        skill = Skill(name="test_tool")
        clean_registry.register(skill)
        assert clean_registry.get("test_tool") is skill

    def test_register_duplicate_raises(self, clean_registry):
        clean_registry.register(Skill(name="dup"))
        with pytest.raises(ValueError, match="already registered"):
            clean_registry.register(Skill(name="dup"))

    def test_register_or_replace(self, clean_registry):
        original = Skill(name="tool", description="original")
        replacement = Skill(name="tool", description="replacement")
        clean_registry.register(original)
        clean_registry.register_or_replace(replacement)
        assert clean_registry.get("tool").description == "replacement"

    def test_unregister(self, clean_registry):
        clean_registry.register(Skill(name="temp"))
        clean_registry.unregister("temp")
        assert clean_registry.get("temp") is None

    def test_unregister_missing_raises(self, clean_registry):
        with pytest.raises(KeyError):
            clean_registry.unregister("nope")

    def test_list_all(self, clean_registry):
        clean_registry.register(Skill(name="a", category="web"))
        clean_registry.register(Skill(name="b", category="system"))
        names = [s.name for s in clean_registry.list()]
        assert sorted(names) == ["a", "b"]

    def test_list_by_category(self, clean_registry):
        clean_registry.register(Skill(name="a", category="web"))
        clean_registry.register(Skill(name="b", category="system"))
        web_skills = clean_registry.list(category="web")
        assert len(web_skills) == 1
        assert web_skills[0].name == "a"

    def test_names(self, clean_registry):
        clean_registry.register(Skill(name="x"))
        clean_registry.register(Skill(name="y"))
        assert sorted(clean_registry.names()) == ["x", "y"]

    def test_count(self, clean_registry):
        assert clean_registry.count() == 0
        clean_registry.register(Skill(name="a"))
        assert clean_registry.count() == 1

    def test_get_skiplist(self, clean_registry):
        clean_registry.register(Skill(name="critical_a", critical=True))
        clean_registry.register(Skill(name="noncrit_b", critical=False))
        clean_registry.register(Skill(name="noncrit_c", critical=False))
        skiplist = clean_registry.get_skiplist()
        assert "critical_a" not in skiplist
        assert "noncrit_b" in skiplist
        assert "noncrit_c" in skiplist
        assert len(skiplist) == 2

    def test_get_skiplist_empty(self, clean_registry):
        assert clean_registry.get_skiplist() == set()

    def test_to_planner_prompt_empty(self, clean_registry):
        prompt = clean_registry.to_planner_prompt()
        assert "No tools available" in prompt

    def test_to_planner_prompt_with_skills(self, clean_registry):
        clean_registry.register(
            Skill(name="alpha", description="First tool", parameters=[SkillParameter("q", "string", True, "query")])
        )
        prompt = clean_registry.to_planner_prompt()
        assert "AVAILABLE TOOLS AND THEIR PARAMETERS" in prompt
        assert "alpha" in prompt
        assert "First tool" in prompt
        assert "q" in prompt

    def test_summary(self, clean_registry):
        clean_registry.register(Skill(name="sum_test", description="Sum test"))
        summary = clean_registry.summary()
        assert len(summary) == 1
        assert summary[0]["name"] == "sum_test"

    def test_clear(self, clean_registry):
        clean_registry.register(Skill(name="a"))
        clean_registry.register(Skill(name="b"))
        clean_registry.clear()
        assert clean_registry.count() == 0

    def test_singleton_same_instance(self):
        """SkillRegistry() and get_skill_registry() should return the same object."""
        a = SkillRegistry()
        b = get_skill_registry()
        assert a is b


# ─── register_builtin_skills ──────────────────────────────────────────────


class TestRegisterBuiltinSkills:
    """Tests for register_builtin_skills()."""

    def test_registers_all_builtins(self, clean_registry):
        register_builtin_skills(clean_registry)
        assert clean_registry.count() == 9

    def test_includes_expected_tools(self, clean_registry):
        register_builtin_skills(clean_registry)
        names = set(clean_registry.names())
        expected = {"web_search", "launch_app", "system_command", "create_file",
                    "read_file", "get_weather", "browse_url", "send_message", "check_trends"}
        assert names == expected

    def test_web_search_is_critical(self, clean_registry):
        register_builtin_skills(clean_registry)
        skill = clean_registry.get("web_search")
        assert skill.critical is True
        assert skill.category == "web"

    def test_read_file_is_noncritical(self, clean_registry):
        register_builtin_skills(clean_registry)
        skill = clean_registry.get("read_file")
        assert skill.critical is False

    def test_skiplist_after_builtins(self, clean_registry):
        register_builtin_skills(clean_registry)
        skiplist = clean_registry.get_skiplist()
        # Non-critical tools
        assert "read_file" in skiplist
        assert "get_weather" in skiplist
        assert "browse_url" in skiplist
        assert "send_message" in skiplist
        assert "check_trends" in skiplist
        # Critical tools
        assert "web_search" not in skiplist
        assert "launch_app" not in skiplist
        assert len(skiplist) == 5

    def test_idempotent(self, clean_registry):
        register_builtin_skills(clean_registry)
        register_builtin_skills(clean_registry)
        # Should still be 9, not 18 (duplicates silently ignored)
        assert clean_registry.count() == 9


# ─── create_skill_from_handler ──────────────────────────────────────────────


class TestCreateSkillFromHandler:
    """Tests for the create_skill_from_handler() helper."""

    async def _dummy_handler(self, **kwargs) -> str:
        return f"handled: {kwargs}"

    def test_creates_skill_with_handler(self):
        skill = create_skill_from_handler(
            name="my_plugin",
            handler=self._dummy_handler,
            description="A plugin skill",
            parameters=[SkillParameter("input", "string", True, "Input value")],
            critical=False,
            category="custom",
        )
        assert skill.name == "my_plugin"
        assert skill.handler is not None
        assert skill.description == "A plugin skill"
        assert len(skill.parameters) == 1
        assert skill.critical is False
        assert skill.category == "custom"
        assert skill.metadata == {"source": "plugin"}

    def test_creates_skill_minimal(self):
        skill = create_skill_from_handler(name="minimal", handler=self._dummy_handler)
        assert skill.name == "minimal"
        assert skill.description == ""
        assert skill.parameters == []
        assert skill.critical is True
        assert skill.category == "custom"

    async def test_handler_is_callable(self):
        skill = create_skill_from_handler(name="test_handler", handler=self._dummy_handler)
        result = await skill.handler(input="hello")
        assert result == "handled: {'input': 'hello'}"


# ─── Planner Prompt Integration ────────────────────────────────────────────


class TestPlannerPromptIntegration:
    """Tests that the planner prompt generation integrates correctly."""

    def test_prompt_has_skill_list(self, clean_registry):
        """The generated prompt should include the skill listing."""
        from agent.agent_planner import _get_planner_system_prompt
        clean_registry.clear()
        register_builtin_skills(clean_registry)
        prompt = _get_planner_system_prompt()
        assert "AVAILABLE TOOLS AND THEIR PARAMETERS" in prompt
        assert "web_search" in prompt
        assert "system_command" in prompt
        assert "OUTPUT" in prompt

    def test_prompt_json_example_readable(self, clean_registry):
        """The JSON output example in the prompt should be well-formed looking."""
        from agent.agent_planner import _get_planner_system_prompt
        clean_registry.clear()
        register_builtin_skills(clean_registry)
        prompt = _get_planner_system_prompt()
        # Should have a { on its own line (not {})
        assert '"goal"' in prompt
        assert '"steps"' in prompt
        assert '"tool"' in prompt
        assert '"parameters"' in prompt
        assert '"critical"' in prompt
