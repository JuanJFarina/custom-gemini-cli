from asyncio import CancelledError, Lock, Task, create_task, sleep
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from asyncpg import PostgresError

from harle_utils import MessageDeliveryError, log

from .notifications import EventNotificationService
from .service import EventService

SCHEDULER_FAILURES = (
    MessageDeliveryError,
    OSError,
    PostgresError,
    RuntimeError,
    TypeError,
    ValueError,
)


@dataclass(slots=True)
class AgentsScheduler:
    events: EventService
    notifications: EventNotificationService
    interval_seconds: float = 300
    sleeper: Callable[[float], Awaitable[None]] = sleep
    _task: Task[None] | None = field(default=None, init=False)
    _run_lock: Lock = field(default_factory=Lock, init=False)

    def __post_init__(self) -> None:
        if self.interval_seconds <= 0:
            raise ValueError("Scheduler interval must be positive.")

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = create_task(self.run_forever())

    async def stop(self) -> None:
        task = self._task
        if task is None:
            return
        self._task = None
        task.cancel()
        try:
            await task
        except CancelledError:
            pass

    async def run_forever(self) -> None:
        while True:
            try:
                await self.run_once()
            except SCHEDULER_FAILURES as exc:
                log.warning("Event scheduler pass failed: %s", type(exc).__name__)
            await self.sleeper(self.interval_seconds)

    async def run_once(self) -> int:
        async with self._run_lock:
            due_events = await self.events.list_due_for_notification()
            notified_count = 0
            for event in due_events:
                try:
                    delivered = await self.notifications.notify(event)
                    if not delivered:
                        continue
                    notified = await self.events.mark_notified(event=event)
                    notified_count += notified is not None
                except SCHEDULER_FAILURES as exc:
                    log.warning(
                        "Event notification failed for %s: %s",
                        event.id,
                        type(exc).__name__,
                    )
            return notified_count
