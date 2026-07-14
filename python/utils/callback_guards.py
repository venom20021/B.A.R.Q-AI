"""
Runtime guard: enforces that sync callback slots never receive async functions.

Usage::

    from utils.callback_guards import SyncCallback

    class MyClass:
        on_event = SyncCallback()

        def __init__(self):
            self.on_event = some_function   # ✅ OK if sync
            self.on_event = some_async_fn   # ❌ TypeError at assignment!

The check happens at **assignment time** — the moment someone writes
``obj.on_event = some_async_fn`` — so the error is caught immediately
and cannot be missed.

Thread-safety note: The descriptor is safe for single-threaded access.
For fields that are read from daemon threads (e.g. WakeWordDetector),
the guard only protects the *assignment*; the read still happens in
the thread's own context.
"""

import inspect
from typing import Any, Optional


class SyncCallback:
    """Descriptor that prevents assigning async functions to sync callback slots.

    Add to a class body to declare a sync callback field::

        class MyClass:
            on_event = SyncCallback()

        obj = MyClass()
        obj.on_event = some_sync_function   # ✅ OK
        obj.on_event = some_async_function  # ❌ TypeError

    Accepts ``None`` as a valid value (callback not set).
    """

    def __set_name__(self, owner: type, name: str) -> None:
        self._name = name

    def __get__(self, obj: Any, objtype: Optional[type] = None) -> Any:
        if obj is None:
            return self
        return obj.__dict__.get(self._name)

    def __set__(self, obj: Any, value: Any) -> None:
        if value is not None and inspect.iscoroutinefunction(value):
            raise TypeError(
                f"Cannot assign async function '{value.__name__}' to sync callback "
                f"'{self._name}' on {type(obj).__name__}. "
                f"Sync callbacks must be regular (non-async) functions."
            )
        obj.__dict__[self._name] = value
