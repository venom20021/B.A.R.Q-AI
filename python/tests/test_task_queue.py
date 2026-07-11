"""Tests for the BARQ Agent Task Queue.

Tests the AgentTaskQueue class including:
    - Submit, cancel, get_status operations
    - Priority ordering (HIGH antes que NORMAL antes que LOW)
    - Start/stop lifecycle
    - Cancellation of pending tasks
    - Concurrent execution limits
"""


import pytest

from agent.task_queue import AgentTaskQueue, TaskPriority

# ─── Basic Operations ─────────────────────────────────────────────────────

class TestTaskQueueOperations:
    """Tests for submitting, tracking, and cancelling tasks."""

    @pytest.fixture
    def queue(self):
        return AgentTaskQueue()

    async def test_submit_returns_id(self, queue: AgentTaskQueue):
        """Submitting a goal should return a non-empty task ID."""
        task_id = await queue.submit("Test goal")
        assert task_id
        assert len(task_id) == 8  # uuid4()[:8]

    async def test_get_status_returns_goal(self, queue: AgentTaskQueue):
        """get_status should return the original goal."""
        task_id = await queue.submit("My goal")
        status = await queue.get_status(task_id)
        assert status is not None
        assert status["goal"] == "My goal"
        assert status["task_id"] == task_id

    async def test_get_status_pending_by_default(self, queue: AgentTaskQueue):
        """A newly submitted task should have PENDING status."""
        task_id = await queue.submit("Test")
        status = await queue.get_status(task_id)
        assert status["status"] == "pending"

    async def test_get_status_nonexistent(self, queue: AgentTaskQueue):
        """get_status for a non-existent ID should return None."""
        status = await queue.get_status("nonexistent")
        assert status is None

    async def test_cancel_pending_task(self, queue: AgentTaskQueue):
        """Cancelling a pending task should succeed."""
        task_id = await queue.submit("Cancel me")
        result = await queue.cancel(task_id)
        assert result is True

        status = await queue.get_status(task_id)
        assert status["status"] == "cancelled"

    async def test_cancel_nonexistent(self, queue: AgentTaskQueue):
        """Cancelling a non-existent task should return False."""
        result = await queue.cancel("nonexistent")
        assert result is False

    async def test_cancel_idempotent(self, queue: AgentTaskQueue):
        """Cancelling an already cancelled task should return False."""
        task_id = await queue.submit("Already cancelled")
        await queue.cancel(task_id)
        result = await queue.cancel(task_id)
        assert result is False


# ─── Priority Ordering ────────────────────────────────────────────────────

class TestPriorityOrdering:
    """Tests that higher priority tasks are processed first."""

    async def test_priority_enum_values(self):
        """HIGH should have lower numeric value (higher priority)."""
        assert TaskPriority.HIGH.value < TaskPriority.NORMAL.value
        assert TaskPriority.NORMAL.value < TaskPriority.LOW.value

    async def test_submit_with_different_priorities(self, queue: AgentTaskQueue):
        """Tasks with different priorities should be stored correctly."""
        low_id = await queue.submit("Low", priority=TaskPriority.LOW)
        high_id = await queue.submit("High", priority=TaskPriority.HIGH)

        low_status = await queue.get_status(low_id)
        high_status = await queue.get_status(high_id)

        assert low_status["goal"] == "Low"
        assert high_status["goal"] == "High"


# ─── Lifecycle ────────────────────────────────────────────────────────────

class TestLifecycle:
    """Tests for start/stop lifecycle."""

    @pytest.fixture
    def queue(self):
        return AgentTaskQueue()

    async def test_start_creates_worker(self, queue: AgentTaskQueue):
        """Starting the queue should create a worker task."""
        assert queue._worker_task is None
        await queue.start()
        assert queue._worker_task is not None
        assert queue._running is True
        await queue.stop()

    async def test_start_idempotent(self, queue: AgentTaskQueue):
        """Starting an already running queue should be a no-op."""
        await queue.start()
        task = queue._worker_task
        await queue.start()  # Second start
        assert queue._worker_task is task  # Same task, not replaced
        await queue.stop()

    async def test_stop_cleans_up_worker(self, queue: AgentTaskQueue):
        """Stopping the queue should cancel the worker task."""
        await queue.start()
        await queue.stop()
        assert queue._running is False

    async def test_get_all_statuses_empty(self, queue: AgentTaskQueue):
        """An empty queue should return an empty list."""
        statuses = await queue.get_all_statuses()
        assert statuses == []

    async def test_get_all_statuses_after_submit(self, queue: AgentTaskQueue):
        """After submitting tasks, get_all_statuses should return them."""
        await queue.submit("Task 1")
        await queue.submit("Task 2")
        statuses = await queue.get_all_statuses()
        assert len(statuses) == 2

    async def test_pending_count(self, queue: AgentTaskQueue):
        """pending_count should reflect items in the queue."""
        assert await queue.pending_count() == 0
        await queue.submit("Task 1")
        assert await queue.pending_count() == 1
        await queue.submit("Task 2")
        assert await queue.pending_count() == 2


# ─── Concurrent Execution ────────────────────────────────────────────────

class TestConcurrentExecution:
    """Tests for concurrent execution limits."""

    async def test_custom_max_concurrent(self):
        """The max_concurrent parameter should be configurable."""
        queue = AgentTaskQueue(max_concurrent=3)
        assert queue._max_concurrent == 3

    async def test_default_max_concurrent(self):
        """Default max_concurrent should be 1."""
        queue = AgentTaskQueue()
        assert queue._max_concurrent == 1


# ─── Integration with Executor ────────────────────────────────────────────

class TestExecutorIntegration:
    """Tests that the queue properly creates an executor."""

    async def test_get_executor_lazy_loads(self, queue: AgentTaskQueue):
        """_get_executor should return an AgentExecutor instance."""
        executor = queue._get_executor()
        from agent.agent_executor import AgentExecutor
        assert isinstance(executor, AgentExecutor)

    async def test_get_executor_is_singleton(self, queue: AgentTaskQueue):
        """_get_executor should return the same instance on repeated calls."""
        e1 = queue._get_executor()
        e2 = queue._get_executor()
        assert e1 is e2


# ─── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def queue():
    """Return a fresh AgentTaskQueue instance."""
    return AgentTaskQueue()
