import asyncio
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

from harle_domain.events import InternalEvent
from harle_services.events import (
    AgentsScheduler,
    EventNotificationService,
    EventService,
)


class FakeEvents:
    def __init__(self, events: list[InternalEvent]) -> None:
        self.events = events
        self.marked: set[UUID] = set()

    async def list_due_for_notification(self) -> list[InternalEvent]:
        return [event for event in self.events if event.id not in self.marked]

    async def mark_notification_delivered(
        self,
        *,
        event: InternalEvent,
    ) -> InternalEvent:
        self.marked.add(event.id)
        return event


class FakeNotifications:
    def __init__(self, outcomes: list[bool]) -> None:
        self.outcomes = outcomes
        self.attempts: list[UUID] = []

    async def notify(self, event: InternalEvent) -> bool:
        self.attempts.append(event.id)
        return self.outcomes.pop(0)


def test_scheduler_marks_success_and_retries_failed_delivery() -> None:
    async def verify() -> None:
        first = cast(InternalEvent, SimpleNamespace(id=uuid4()))
        second = cast(InternalEvent, SimpleNamespace(id=uuid4()))
        events = FakeEvents([first, second])
        notifications = FakeNotifications([True, False])
        scheduler = AgentsScheduler(
            events=cast(EventService, events),
            notifications=cast(EventNotificationService, notifications),
        )

        assert await scheduler.run_once() == 1
        assert events.marked == {first.id}

        notifications.outcomes.append(True)
        assert await scheduler.run_once() == 1
        assert events.marked == {first.id, second.id}
        assert notifications.attempts == [first.id, second.id, second.id]

    asyncio.run(verify())
