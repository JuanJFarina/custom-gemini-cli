import asyncio
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

from harle_domain.events import InteractionEvent, InternalEvent
from harle_services.events import (
    AgentsScheduler,
    EventNotificationOutcome,
    EventNotificationService,
    EventService,
    InteractionEventService,
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
    def __init__(self, outcomes: list[EventNotificationOutcome]) -> None:
        self.outcomes = outcomes
        self.attempts: list[UUID] = []
        self.interaction_attempts: list[UUID] = []

    async def notify(self, event: InternalEvent) -> EventNotificationOutcome:
        self.attempts.append(event.id)
        return self.outcomes.pop(0)

    async def notify_interaction(
        self,
        event: InteractionEvent,
    ) -> EventNotificationOutcome:
        self.interaction_attempts.append(event.id)
        return EventNotificationOutcome.DELIVERED


class FakeInteractions:
    def __init__(self, events: list[InteractionEvent] | None = None) -> None:
        self.events = events or []
        self.checked: list[UUID] = []

    async def list_active(self) -> list[InteractionEvent]:
        return list(self.events)

    def should_trigger(
        self,
        event: InteractionEvent,
        **_: object,
    ) -> bool:
        self.checked.append(event.id)
        return True


def test_scheduler_marks_success_and_retries_failed_delivery() -> None:
    async def verify() -> None:
        user_id = uuid4()
        first = cast(
            InternalEvent,
            SimpleNamespace(id=uuid4(), user_id=user_id),
        )
        second = cast(
            InternalEvent,
            SimpleNamespace(id=uuid4(), user_id=user_id),
        )
        events = FakeEvents([first, second])
        notifications = FakeNotifications(
            [
                EventNotificationOutcome.DELIVERED,
                EventNotificationOutcome.SKIPPED,
            ],
        )
        scheduler = AgentsScheduler(
            events=cast(EventService, events),
            interactions=cast(InteractionEventService, FakeInteractions()),
            notifications=cast(EventNotificationService, notifications),
        )

        assert await scheduler.run_once() == 1
        assert events.marked == {first.id}

        notifications.outcomes.append(EventNotificationOutcome.DELIVERED)
        assert await scheduler.run_once() == 1
        assert events.marked == {first.id, second.id}
        assert notifications.attempts == [first.id, second.id, second.id]

    asyncio.run(verify())


def test_scheduler_suppresses_interaction_only_for_user_with_due_event() -> None:
    async def verify() -> None:
        due_user_id = uuid4()
        available_user_id = uuid4()
        due = cast(
            InternalEvent,
            SimpleNamespace(id=uuid4(), user_id=due_user_id),
        )
        suppressed = cast(
            InteractionEvent,
            SimpleNamespace(id=uuid4(), user_id=due_user_id),
        )
        available = cast(
            InteractionEvent,
            SimpleNamespace(id=uuid4(), user_id=available_user_id),
        )
        interactions = FakeInteractions([suppressed, available])
        notifications = FakeNotifications([EventNotificationOutcome.SKIPPED])
        scheduler = AgentsScheduler(
            events=cast(EventService, FakeEvents([due])),
            interactions=cast(InteractionEventService, interactions),
            notifications=cast(EventNotificationService, notifications),
        )

        assert await scheduler.run_once() == 1
        assert interactions.checked == [available.id]
        assert notifications.interaction_attempts == [available.id]

    asyncio.run(verify())
