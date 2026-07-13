"""Background-task registry.

asyncio keeps only weak references to tasks created with create_task(), so a
fire-and-forget task can be garbage-collected mid-flight and any exception it
raises is dropped silently. spawn() keeps a strong reference until the task
finishes and logs any exception it dies with.
"""

import asyncio

from Emilia import LOGGER

_BACKGROUND_TASKS: "set[asyncio.Task]" = set()


def spawn(coro, *, name: str) -> asyncio.Task:
    task = asyncio.create_task(coro, name=name)
    _BACKGROUND_TASKS.add(task)

    def _done(t: asyncio.Task):
        _BACKGROUND_TASKS.discard(t)
        if not t.cancelled() and t.exception():
            LOGGER.error(f"Background task {t.get_name()} died", exc_info=t.exception())

    task.add_done_callback(_done)
    return task
