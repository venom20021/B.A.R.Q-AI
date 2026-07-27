"""
Tests for AgentKernel, MemoryBus, and Skill Performance Analytics.

These tests verify the three HIGH priority improvements:
1. AgentKernel — LLM queuing, rate limiting, context tracking
2. MemoryBus — unified memory with FTS5 full-text search
3. Skill Performance Analytics — execution metrics tracking
"""

import asyncio
import sqlite3
import time
from pathlib import Path

import pytest

from agent.agent_kernel import AgentKernel, AgentLLMUsage
from agent.skill_registry import (
    SkillExecutionStats,
    SkillRegistry,
    get_skill_registry,
)


# ═══════════════════════════════════════════════════════════════════════════════
# SkillExecutionStats Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSkillExecutionStats:
    """Verify the SkillExecutionStats data class and its derived properties."""

    def test_defaults(self):
        stats = SkillExecutionStats(skill_name="web_search")
        assert stats.total_calls == 0
        assert stats.success_count == 0
        assert stats.error_count == 0
        assert stats.total_duration_seconds == 0.0
        assert stats.success_rate == 0.0
        assert stats.avg_duration == 0.0

    def test_success_rate(self):
        stats = SkillExecutionStats(skill_name="test", total_calls=10, success_count=7)
        assert stats.success_rate == 70.0

    def test_success_rate_all_fail(self):
        stats = SkillExecutionStats(skill_name="test", total_calls=5, success_count=0)
        assert stats.success_rate == 0.0

    def test_avg_duration(self):
        stats = SkillExecutionStats(
            skill_name="test", total_calls=4, total_duration_seconds=10.0
        )
        assert stats.avg_duration == 2.5

    def test_to_dict(self):
        stats = SkillExecutionStats(
            skill_name="test",
            total_calls=5,
            success_count=4,
            error_count=1,
            total_duration_seconds=12.0,
            last_duration_seconds=2.5,
            last_error="timeout error",
            last_called_at=1234567890.0,
            error_patterns={"timeout": 1},
        )
        d = stats.to_dict()
        assert d["skill"] == "test"
        assert d["total_calls"] == 5
        assert d["success_count"] == 4
        assert d["error_count"] == 1
        assert d["success_rate_pct"] == 80.0
        assert d["avg_duration_seconds"] == 2.4
        assert d["last_duration_seconds"] == 2.5
        assert d["last_error"] == "timeout error"
        assert d["error_patterns"]["timeout"] == 1

    def test_error_patterns_overflow_limited_to_10(self):
        patterns = {f"err_{i}": i for i in range(20)}
        stats = SkillExecutionStats(
            skill_name="test",
            total_calls=20,
            error_count=20,
            error_patterns=patterns,
        )
        d = stats.to_dict()
        assert len(d["error_patterns"]) <= 10


# ═══════════════════════════════════════════════════════════════════════════════
# SkillRegistry Performance Analytics Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSkillRegistryAnalytics:
    """Verify the SkillRegistry tracks execution metrics."""

    @pytest.fixture
    def registry(self):
        """Return a fresh registry with one registered skill."""
        reg = SkillRegistry()
        reg.clear()
        from agent.skill_registry import Skill, SkillParameter

        async def _success(**kwargs):
            return "OK"

        async def _failure(**kwargs):
            raise ValueError("Intentional failure")

        reg.register(
            Skill(
                name="test_success",
                description="Always succeeds",
                handler=_success,
                critical=False,
                category="test",
            )
        )
        reg.register(
            Skill(
                name="test_failure",
                description="Always fails",
                handler=_failure,
                critical=False,
                category="test",
            )
        )
        yield reg
        reg.clear()

    @pytest.mark.asyncio
    async def test_records_success(self, registry):
        result = await registry.call("test_success")
        assert result == "OK"
        stats = registry.get_skill_stats("test_success")
        assert stats is not None
        assert stats["total_calls"] == 1
        assert stats["success_count"] == 1
        assert stats["error_count"] == 0
        assert stats["success_rate_pct"] == 100.0

    @pytest.mark.asyncio
    async def test_records_error(self, registry):
        with pytest.raises(RuntimeError, match="test_failure"):
            await registry.call("test_failure")
        stats = registry.get_skill_stats("test_failure")
        assert stats is not None
        assert stats["total_calls"] == 1
        assert stats["success_count"] == 0
        assert stats["error_count"] == 1

    @pytest.mark.asyncio
    async def test_records_duration(self, registry):
        await registry.call("test_success")
        stats = registry.get_skill_stats("test_success")
        # Duration should be recorded (even near-zero for instant handlers)
        assert stats is not None
        assert "last_duration_seconds" in stats

    @pytest.mark.asyncio
    async def test_records_error_pattern(self, registry):
        with pytest.raises(RuntimeError):
            await registry.call("test_failure")
        stats = registry.get_skill_stats("test_failure")
        assert "Intentional failure" in stats["last_error"]
        # Error pattern key should be first 40 chars
        assert any("intentional" in k for k in stats["error_patterns"])

    @pytest.mark.asyncio
    async def test_get_all_stats_sorted(self, registry):
        await registry.call("test_success")
        with pytest.raises(RuntimeError):
            await registry.call("test_failure")
        all_stats = registry.get_all_stats()
        # Both skills with equal call count should appear
        skill_names = {s["skill"] for s in all_stats}
        assert skill_names == {"test_success", "test_failure"}
        # Both have total_calls = 1 (order not guaranteed for ties)

    @pytest.mark.asyncio
    async def test_stats_summary(self, registry):
        await registry.call("test_success")
        with pytest.raises(RuntimeError):
            await registry.call("test_failure")
        summary = registry.get_stats_summary()
        assert summary["total_executions"] == 2
        assert summary["total_successes"] == 1
        assert summary["total_errors"] == 1
        assert summary["avg_success_rate_pct"] == 50.0
        assert summary["active_skills"] == 2

    def test_unknown_skill_returns_none(self, registry):
        stats = registry.get_skill_stats("nonexistent")
        assert stats is None


# ═══════════════════════════════════════════════════════════════════════════════
# AgentKernel Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestAgentKernel:
    """Verify the AgentKernel's core features: rate limiting, context tracking, stats."""

    @pytest.fixture
    def kernel(self):
        """Create a test kernel with low thresholds to exercise rate limiting."""
        k = AgentKernel(
            max_concurrent=2,
            rate_limit_calls=3,
            rate_limit_window=60,
            max_context_tokens=4096,
        )
        k.start()
        yield k
        # Cleanup
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(k.stop())
        else:
            loop.run_until_complete(k.stop())

    @pytest.mark.asyncio
    async def test_concurrency_semaphore(self, kernel):
        """Max concurrent is 2, ensure semaphore limits concurrent access."""
        assert kernel._semaphore._value == 2  # type: ignore

        # Verify that acquired semaphore blocks access
        async def acquire_and_hold():
            async with kernel._semaphore:
                await asyncio.sleep(0.1)
                return True

        # Launch 4 concurrent tasks - only 2 should run at once
        tasks = [asyncio.create_task(acquire_and_hold()) for _ in range(4)]
        done, pending = await asyncio.wait(tasks, timeout=0.3)
        assert len(done) == 4, "All 4 tasks should complete given enough time"

    @pytest.mark.asyncio
    async def test_rate_limiting(self, kernel):
        """Rate limit of 3 calls per 60s window should allow 3 then block."""
        # Mark 3 timestamps using the proper AgentLLMUsage class
        usage = AgentLLMUsage(agent_name="test_agent")
        usage.call_timestamps = [time.time() - 2, time.time() - 1, time.time() - 0.5]
        usage.total_calls = 3
        kernel._agent_usage["test_agent"] = usage

        allowed = await kernel._check_rate_limit("test_agent")
        assert not allowed, "Should be rate limited after 3 calls in 60s"

    @pytest.mark.asyncio
    async def test_rate_limiting_old_timestamps_pruned(self, kernel):
        """Timestamps older than the window should be pruned."""
        usage = AgentLLMUsage(agent_name="test_agent")
        usage.call_timestamps = [time.time() - 120, time.time() - 90]
        usage.total_calls = 2
        kernel._agent_usage["test_agent"] = usage

        allowed = await kernel._check_rate_limit("test_agent")
        assert allowed, "Should allow after pruning old timestamps"

    @pytest.mark.asyncio
    async def test_context_window(self, kernel):
        """Opening a context window, updating it, and querying it works."""
        cw = await kernel.open_context("conv_1", "test_agent", max_tokens=4096)
        assert cw.conversation_id == "conv_1"
        assert cw.agent_name == "test_agent"
        assert cw.tokens_used == 0

        # Simulate updating with messages
        await kernel._update_context_window(
            "conv_1",
            "test_agent",
            [{"role": "user", "content": "Hello " * 100}],  # ~100 chars → ~25 tokens
        )
        usage = await kernel.get_context_usage("conv_1")
        assert usage is not None
        assert usage["tokens_used"] > 0

    @pytest.mark.asyncio
    async def test_close_context(self, kernel):
        await kernel.open_context("conv_2", "test_agent")
        await kernel.close_context("conv_2")
        usage = await kernel.get_context_usage("conv_2")
        assert usage is None

    @pytest.mark.asyncio
    async def test_agent_stats_empty(self, kernel):
        stats = await kernel.get_agent_stats("nonexistent")
        assert stats is None

    @pytest.mark.asyncio
    async def test_record_usage(self, kernel):
        await kernel._record_success(
            "agent1",
            [{"role": "user", "content": "test"}],
            "response text",
            duration=0.5,
        )
        stats = await kernel.get_agent_stats("agent1")
        assert stats is not None
        assert stats["total_calls"] == 1
        assert stats["total_duration_seconds"] == 0.5
        assert stats["avg_duration_seconds"] == 0.5

    @pytest.mark.asyncio
    async def test_record_error(self, kernel):
        await kernel._record_error("agent2", "timeout error")
        stats = await kernel.get_agent_stats("agent2")
        assert stats is not None
        assert stats["total_calls"] == 1
        assert stats["errors"] == 1

    @pytest.mark.asyncio
    async def test_get_status(self, kernel):
        status = await kernel.get_status()
        assert status["status"] == "running"
        assert status["max_concurrent"] == 2
        assert "semaphore_available" in status
        assert "active_agents" in status


# ═══════════════════════════════════════════════════════════════════════════════
# MemoryBus Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestMemoryBus:
    """Verify MemoryBus with SQLite FTS5 — store, search, recall, forget, TTL."""

    @pytest.fixture
    def bus(self, tmp_path):
        """Create a MemoryBus backed by a temp file."""
        from memory.memory_bus import MemoryBus

        db_path = str(tmp_path / "test_memory_bus.db")
        b = MemoryBus(db_path=db_path)
        b.start()
        yield b
        # Cleanup
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(b.stop())
        else:
            loop.run_until_complete(b.stop())

    @pytest.mark.asyncio
    async def test_store_and_recall(self, bus):
        memory_id = await bus.store("favorite_color", "blue", category="preferences")
        assert memory_id is not None
        assert len(memory_id) > 0

        value = await bus.recall("favorite_color")
        assert value == "blue"

    @pytest.mark.asyncio
    async def test_store_and_get_by_id(self, bus):
        memory_id = await bus.store("test_key", "test_value")
        entry = await bus.get(memory_id)
        assert entry is not None
        assert entry["key"] == "test_key"
        assert entry["value"] == "test_value"

    @pytest.mark.asyncio
    async def test_recall_nonexistent(self, bus):
        value = await bus.recall("nonexistent")
        assert value is None

    @pytest.mark.asyncio
    async def test_forget(self, bus):
        await bus.store("secret", "hidden", category="notes")
        assert await bus.recall("secret") == "hidden"
        found = await bus.forget("secret")
        assert found is True
        assert await bus.recall("secret") is None

    @pytest.mark.asyncio
    async def test_forget_nonexistent(self, bus):
        found = await bus.forget("nonexistent")
        assert found is False

    @pytest.mark.asyncio
    async def test_forget_with_category(self, bus):
        await bus.store("key1", "value1", category="cat_a")
        await bus.store("key1", "value2", category="cat_b")
        found = await bus.forget("key1", category="cat_a")
        assert found is True
        assert await bus.recall("key1", category="cat_b") == "value2"
        assert await bus.recall("key1", category="cat_a") is None

    @pytest.mark.asyncio
    async def test_search_fts(self, bus):
        await bus.store("username", "Alice Johnson", category="identity", tags=["person"])
        await bus.store("pet_name", "Fluffy", category="preferences", tags=["pet"])

        results = await bus.search("Alice")
        assert len(results) >= 1
        assert any(r["key"] == "username" for r in results)

    @pytest.mark.asyncio
    async def test_search_empty(self, bus):
        results = await bus.search("ZzZzNotPresent")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_search_with_category_filter(self, bus):
        await bus.store("data1", "needle", category="identity")
        await bus.store("data2", "needle", category="projects")
        results = await bus.search("needle", category="identity")
        assert len(results) >= 1
        assert all(r["category"] == "identity" for r in results)

    @pytest.mark.asyncio
    async def test_search_with_tags(self, bus):
        await bus.store("item1", "tagged value", tags=["important", "work"])
        await bus.store("item2", "other value", tags=["personal"])
        results = await bus.search("value", tags=["important"])
        assert len(results) >= 1
        assert results[0]["key"] == "item1"

    @pytest.mark.asyncio
    async def test_remember_convenience(self, bus):
        memory_id = await bus.remember("quick_note", "Remember this", category="notes")
        assert memory_id is not None
        value = await bus.recall("quick_note")
        assert value == "Remember this"

    @pytest.mark.asyncio
    async def test_list_by_category(self, bus):
        await bus.store("a", "1", category="cat_x")
        await bus.store("b", "2", category="cat_x")
        await bus.store("c", "3", category="cat_y")
        entries = await bus.list_by_category("cat_x")
        assert len(entries) == 2
        assert all(e["category"] == "cat_x" for e in entries)

    @pytest.mark.asyncio
    async def test_format_for_prompt(self, bus):
        await bus.store("color", "green", category="preferences")
        await bus.store("name", "Test User", category="identity")
        prompt_text = bus.format_for_prompt()
        assert "green" in prompt_text
        assert "Test User" in prompt_text
        assert "Memory" in prompt_text or "PREFERENCES" in prompt_text or "IDENTITY" in prompt_text

    @pytest.mark.asyncio
    async def test_format_for_prompt_with_category(self, bus):
        await bus.store("color", "red", category="preferences")
        await bus.store("name", "User", category="identity")
        prompt_text = bus.format_for_prompt(category="preferences")
        assert "red" in prompt_text
        assert "User" not in prompt_text  # Filtered to category

    @pytest.mark.asyncio
    async def test_ttl_expiration(self, bus):
        """Memories with TTL should expire and not appear in search after."""
        await bus.store("ephemeral", "gone soon", ttl_seconds=0.01)  # 10ms TTL
        import asyncio
        await asyncio.sleep(0.05)  # Wait for expiration
        value = await bus.recall("ephemeral")
        assert value is None, "TTL-expired memory should not be recallable"

    @pytest.mark.asyncio
    async def test_memory_without_ttl_lasts_forever(self, bus):
        """Memories without TTL should not expire."""
        await bus.store("permanent", "stays forever", ttl_seconds=None)
        import asyncio
        await asyncio.sleep(0.05)
        value = await bus.recall("permanent")
        assert value == "stays forever"

    @pytest.mark.asyncio
    async def test_get_stats(self, bus):
        await bus.store("a", "1", category="stats_test")
        await bus.store("b", "2", category="stats_test")
        stats = await bus.get_stats()
        assert stats["total_active"] >= 2
        assert stats["fts5_enabled"] is True
        assert "stats_test" in stats["categories"]

    def test_fts5_table_created(self, tmp_path):
        """Verify the FTS5 virtual table exists in the database."""
        from memory.memory_bus import MemoryBus
        db_path = str(tmp_path / "fts_test.db")
        bus = MemoryBus(db_path=db_path)
        bus.start()
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='memory_fts'"
            )
            assert cursor.fetchone() is not None, "FTS5 table should exist"
        bus.stop()
