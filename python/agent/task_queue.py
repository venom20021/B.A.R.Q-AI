"""
BARQ Agent Task Queue — priority-based background task execution.

Manages a queue of autonomous tasks that can run in the background while
the user continues interacting with BARQ.  Supports priority levels,
cancellation, status tracking, and concurrent execution limits.

Inspired by MARK XXXIX-OR's task_queue.py but adapted for BARQ's
async-first architecture.
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class TaskStatus(Enum):
    """Status of a queued task."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(Enum):
    """Priority levels for task scheduling.

    Lower numeric value = higher priority.
    """
    LOW = 3
    NORMAL = 2
    HIGH = 1


@dataclass(order=True)
class Task:
    """A single queued task instance."""
    priority: int  # Lower = higher priority
    created_at: float = field(compare=False)
    task_id: str = field(compare=False)
    goal: str = field(compare=False)
    status: TaskStatus = field(compare=False, default=TaskStatus.PENDING)
    result: Any = field(compare=False, default=None)
    error: str = field(compare=False, default="")
    cancel_flag: asyncio.Event = field(compare=False, default_factory=asyncio.Event)


class AgentTaskQueue:
    """Async priority-based task queue for background agent execution.

    Usage::

        queue = AgentTaskQueue()
        task_id = await queue.submit("Research topic X and save to file", priority=TaskPriority.HIGH)
        status = await queue.get_status(task_id)
    """

    def __init__(self, max_concurrent: int = 1):
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._tasks: dict[str, Task] = {}
        self._running: bool = False
        self._max_concurrent = max_concurrent
        self._active_count = 0
        self._lock = asyncio.Lock()
        self._worker_task: Optional[asyncio.Task] = None
        self._executor: Optional[Any] = None

    def _get_executor(self):
        """Lazy-import the executor to avoid circular imports."""
        if self._executor is None:
            from .agent_executor import AgentExecutor
            self._executor = AgentExecutor()
        return self._executor

    async def start(self) -> None:
        """Start the background worker loop."""
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop())
        print("[AgentTaskQueue] OK Started")

    async def stop(self) -> None:
        """Stop the worker loop gracefully."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
        print("[AgentTaskQueue] STOP Stopped")

    async def submit(
        self,
        goal: str,
        priority: TaskPriority = TaskPriority.NORMAL,
    ) -> str:
        """Submit a new goal for background execution.

        Args:
            goal: The user's high-level goal.
            priority: Priority level (default: NORMAL).

        Returns:
            A task ID string that can be used to track status.
        """
        task_id = str(uuid.uuid4())[:8]
        task = Task(
            priority=priority.value,
            created_at=time.time(),
            task_id=task_id,
            goal=goal,
        )

        await self._queue.put(task)

        async with self._lock:
            self._tasks[task_id] = task

        print(f"[AgentTaskQueue] QUEUED: [{task_id}] {goal[:60]}...")
        return task_id

    async def cancel(self, task_id: str) -> bool:
        """Cancel a queued or running task.

        Args:
            task_id: The task ID to cancel.

        Returns:
            True if the task was found and cancelled.
        """
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                return False

            task.cancel_flag.set()
            task.status = TaskStatus.CANCELLED
            print(f"[AgentTaskQueue] CANCELLED: [{task_id}]")
            return True

    async def get_status(self, task_id: str) -> Optional[dict]:
        """Get the current status of a task.

        Args:
            task_id: The task ID to query.

        Returns:
            Dict with task_id, goal, status, result, error, or None if not found.
        """
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            return {
                "task_id": task.task_id,
                "goal": task.goal,
                "status": task.status.value,
                "result": task.result,
                "error": task.error,
            }

    async def get_all_statuses(self) -> list[dict]:
        """Get status of all tasks (pending, running, completed)."""
        async with self._lock:
            return [
                {
                    "task_id": t.task_id,
                    "goal": t.goal[:60],
                    "status": t.status.value,
                }
                for t in self._tasks.values()
            ]

    async def pending_count(self) -> int:
        """Get the number of pending tasks."""
        return self._queue.qsize()

    async def _worker_loop(self) -> None:
        """Main worker loop: pull tasks from queue and execute them."""
        while self._running:
            try:
                # Wait for a task to become available
                task: Task = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0
                )

                # Check if already cancelled before starting
                if task.cancel_flag.is_set():
                    task.status = TaskStatus.CANCELLED
                    continue

                # Wait for capacity
                while self._active_count >= self._max_concurrent:
                    await asyncio.sleep(0.1)
                    if not self._running:
                        return

                # Execute in a separate task
                async with self._lock:
                    self._active_count += 1
                    task.status = TaskStatus.RUNNING

                asyncio.create_task(self._run_task(task))

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[AgentTaskQueue] WARN Worker error: {e}")

    async def _run_task(self, task: Task) -> None:
        """Execute a single task in the background."""
        print(f"[AgentTaskQueue] RUNNING: [{task.task_id}] {task.goal[:60]}...")
        try:
            executor = self._get_executor()
            result = await executor.execute(
                goal=task.goal,
                cancel_flag=task.cancel_flag,
            )

            async with self._lock:
                if task.cancel_flag.is_set():
                    task.status = TaskStatus.CANCELLED
                else:
                    task.status = TaskStatus.COMPLETED
                    task.result = result
                self._active_count -= 1

            print(f"[AgentTaskQueue] OK Completed: [{task.task_id}]")

        except Exception as e:
            async with self._lock:
                task.status = TaskStatus.FAILED
                task.error = str(e)
                self._active_count -= 1
            print(f"[AgentTaskQueue] FAIL Failed: [{task.task_id}] {e}")


# Singleton instance for the application
_queue: Optional[AgentTaskQueue] = None


def get_task_queue() -> AgentTaskQueue:
    """Get or create the global AgentTaskQueue singleton."""
    global _queue
    if _queue is None:
        _queue = AgentTaskQueue()
    return _queue
