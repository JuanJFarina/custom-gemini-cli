import asyncio
from collections.abc import MutableMapping, Sequence
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from harle_domain.events import (
    EventStatus,
    EventType,
    InternalEvent,
    NotificationStatus,
    all_day_event_interval,
    timed_event_interval,
)
from harle_services.events import (
    AllDayEventSchedule,
    CreateEvent,
    EventQuery,
    EventService,
    TimedEventSchedule,
    UpdateEvent,
)
from harle_services.tools.internal_events import CreateEventArgs, UpdateEventArgs

NOW = datetime(2026, 8, 31, 12, tzinfo=timezone.utc)


class FakeEventRepository:
    def __init__(self) -> None:
        self.events: MutableMapping[UUID, InternalEvent] = {}

    async def create(
        self,
        *,
        user_id: UUID,
        event: InternalEvent,
    ) -> InternalEvent:
        assert event.user_id == user_id
        self.events[event.id] = event
        return event

    async def get(
        self,
        *,
        user_id: UUID,
        event_id: UUID,
        include_cancelled: bool = False,
    ) -> InternalEvent | None:
        event = self.events.get(event_id)
        if event is None or event.user_id != user_id:
            return None
        if event.status is EventStatus.SCHEDULED:
            return event
        if include_cancelled and event.status is EventStatus.CANCELLED:
            return event
        return None

    async def list_for_range(
        self,
        *,
        user_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
        include_cancelled: bool = False,
    ) -> Sequence[InternalEvent]:
        return [
            event
            for event in self.events.values()
            if event.user_id == user_id
            and event.starts_at < ends_at
            and event.ends_at > starts_at
            and (
                event.status is EventStatus.SCHEDULED
                or (include_cancelled and event.status is EventStatus.CANCELLED)
            )
        ]

    async def list_due_for_notification(
        self,
        *,
        current_time: datetime,
        limit: int,
    ) -> Sequence[InternalEvent]:
        due = [
            event
            for event in self.events.values()
            if event.status is EventStatus.SCHEDULED
            and event.notification_status is NotificationStatus.PENDING
            and event.notification_window_start <= current_time < event.starts_at
        ]
        return sorted(
            due,
            key=lambda event: (
                event.notification_window_start,
                event.starts_at,
                event.id,
            ),
        )[:limit]

    async def update(
        self,
        *,
        user_id: UUID,
        event: InternalEvent,
    ) -> InternalEvent | None:
        current = await self.get(user_id=user_id, event_id=event.id)
        if current is None:
            return None
        self.events[event.id] = event
        return event

    async def cancel(
        self,
        *,
        user_id: UUID,
        event_id: UUID,
        cancelled_at: datetime,
    ) -> InternalEvent | None:
        current = await self.get(user_id=user_id, event_id=event_id)
        if current is None:
            return None
        cancelled = replace(
            current,
            details=replace(current.details, status=EventStatus.CANCELLED),
            timestamps=replace(
                current.timestamps,
                updated_at=cancelled_at,
                cancelled_at=cancelled_at,
            ),
        )
        self.events[event_id] = cancelled
        return cancelled

    async def mark_notification_delivered(
        self,
        *,
        user_id: UUID,
        event_id: UUID,
        expected_updated_at: datetime,
        updated_at: datetime,
    ) -> InternalEvent | None:
        current = await self.get(user_id=user_id, event_id=event_id)
        if current is None or current.updated_at != expected_updated_at:
            return None
        delivered = replace(
            current,
            notification=replace(
                current.notification,
                status=NotificationStatus.DELIVERED,
            ),
            timestamps=replace(current.timestamps, updated_at=updated_at),
        )
        self.events[event_id] = delivered
        return delivered

    async def delete(
        self,
        *,
        user_id: UUID,
        event_id: UUID,
    ) -> InternalEvent | None:
        current = self.events.get(event_id)
        if current is None or current.user_id != user_id:
            return None
        del self.events[event_id]
        return current


def test_event_intervals_convert_local_and_all_day_boundaries() -> None:
    timed = timed_event_interval(
        starts_at=datetime(2026, 9, 1, 15),
        ends_at=datetime(2026, 9, 1, 16, 30),
        timezone_name="America/Argentina/Cordoba",
    )
    all_day = all_day_event_interval(
        start_date=date(2026, 3, 8),
        end_date=date(2026, 3, 8),
        timezone_name="America/New_York",
    )

    assert timed.starts_at == datetime(2026, 9, 1, 18, tzinfo=timezone.utc)
    assert timed.ends_at == datetime(2026, 9, 1, 19, 30, tzinfo=timezone.utc)
    assert all_day.ends_at - all_day.starts_at == timedelta(hours=23)
    with pytest.raises(ValueError):
        timed_event_interval(
            starts_at=datetime(2026, 9, 1, 16),
            ends_at=datetime(2026, 9, 1, 15),
            timezone_name="UTC",
        )


def test_event_service_isolates_cancellation_and_physical_deletion() -> None:
    async def verify() -> None:
        repository = FakeEventRepository()
        service = EventService(repository, clock=lambda: NOW)
        owner_id = uuid4()
        other_id = uuid4()
        event = await service.create(
            user_id=owner_id,
            event=CreateEvent(
                title="Dentist",
                description="Routine visit",
                schedule=TimedEventSchedule(
                    starts_at=datetime(2026, 9, 1, 15),
                    ends_at=datetime(2026, 9, 1, 16),
                    timezone_name="America/Argentina/Cordoba",
                ),
            ),
        )
        assert event.event_type is EventType.USER_EVENT
        assert event.notification_status is NotificationStatus.PENDING
        assert event.notification_window_start == datetime(
            2026,
            9,
            1,
            17,
            45,
            tzinfo=timezone.utc,
        )
        delivered = await service.mark_notification_delivered(event=event)
        assert delivered is not None
        assert delivered.notification_status is NotificationStatus.DELIVERED

        assert (
            await service.update(
                user_id=other_id,
                event_id=event.id,
                changes=UpdateEvent(title="Changed"),
            )
            is None
        )
        updated = await service.update(
            user_id=owner_id,
            event_id=event.id,
            changes=UpdateEvent(
                title="Updated dentist",
                schedule=AllDayEventSchedule(
                    start_date=date(2026, 9, 2),
                    end_date=date(2026, 9, 2),
                    timezone_name="America/Argentina/Cordoba",
                ),
            ),
        )
        assert updated is not None
        assert updated.title == "Updated dentist"
        assert updated.all_day
        assert updated.notification_status is NotificationStatus.PENDING

        disabled = await service.update(
            user_id=owner_id,
            event_id=event.id,
            changes=UpdateEvent(notifications_enabled=False),
        )
        assert disabled is not None
        assert disabled.notification_status is NotificationStatus.DISABLED
        disabled_rescheduled = await service.update(
            user_id=owner_id,
            event_id=event.id,
            changes=UpdateEvent(
                schedule=TimedEventSchedule(
                    starts_at=datetime(2026, 9, 3, 15),
                    ends_at=datetime(2026, 9, 3, 16),
                    timezone_name="America/Argentina/Cordoba",
                ),
            ),
        )
        assert disabled_rescheduled is not None
        assert disabled_rescheduled.notification_status is NotificationStatus.DISABLED
        reenabled = await service.update(
            user_id=owner_id,
            event_id=event.id,
            changes=UpdateEvent(notifications_enabled=True),
        )
        assert reenabled is not None
        assert reenabled.notification_status is NotificationStatus.PENDING

        cancelled = await service.cancel(user_id=owner_id, event_id=event.id)
        assert cancelled is not None
        assert not await service.list_for_range(
            user_id=owner_id,
            query=EventQuery(
                start_date=date(2026, 9, 1),
                end_date=date(2026, 9, 3),
                timezone_name="America/Argentina/Cordoba",
            ),
        )
        assert await service.list_for_range(
            user_id=owner_id,
            query=EventQuery(
                start_date=date(2026, 9, 1),
                end_date=date(2026, 9, 3),
                timezone_name="America/Argentina/Cordoba",
                include_cancelled=True,
            ),
        )

        deleted = await service.delete(user_id=owner_id, event_id=event.id)
        assert deleted is not None
        assert event.id not in repository.events
        assert not await service.list_for_range(
            user_id=owner_id,
            query=EventQuery(
                start_date=date(2026, 9, 1),
                end_date=date(2026, 9, 3),
                timezone_name="America/Argentina/Cordoba",
                include_cancelled=True,
            ),
        )
        assert await service.delete(user_id=other_id, event_id=event.id) is None

    asyncio.run(verify())


def test_event_service_normalizes_notification_leads() -> None:
    async def verify() -> None:
        repository = FakeEventRepository()
        service = EventService(repository, clock=lambda: NOW)
        owner_id = uuid4()
        schedule = TimedEventSchedule(
            starts_at=datetime(2026, 9, 1, 15),
            ends_at=datetime(2026, 9, 1, 16),
            timezone_name="UTC",
        )
        defaulted = await service.create(
            user_id=owner_id,
            event=CreateEvent(
                title="Default lead",
                description="",
                schedule=schedule,
                notify_before=timedelta(0),
                notifications_enabled=False,
            ),
        )
        custom = await service.create(
            user_id=owner_id,
            event=CreateEvent(
                title="Custom lead",
                description="",
                schedule=schedule,
                notify_before=timedelta(minutes=30),
            ),
        )

        assert defaulted.starts_at - defaulted.notification_window_start == timedelta(
            minutes=15,
        )
        assert defaulted.notification_status is NotificationStatus.DISABLED
        preserved = await service.update(
            user_id=owner_id,
            event_id=custom.id,
            changes=UpdateEvent(title="Preserved lead"),
        )
        assert preserved is not None
        assert preserved.starts_at - preserved.notification_window_start == timedelta(
            minutes=30,
        )
        reset = await service.update(
            user_id=owner_id,
            event_id=custom.id,
            changes=UpdateEvent(notify_before=timedelta(0)),
        )
        assert reset is not None
        assert reset.starts_at - reset.notification_window_start == timedelta(
            minutes=15,
        )
        positive = await service.update(
            user_id=owner_id,
            event_id=custom.id,
            changes=UpdateEvent(notify_before=timedelta(minutes=45)),
        )
        assert positive is not None
        assert positive.starts_at - positive.notification_window_start == timedelta(
            minutes=45,
        )

    asyncio.run(verify())


def test_event_tool_preserves_omitted_zero_and_positive_notification_leads() -> None:
    schedule = {
        "title": "Reminder",
        "starts_at": datetime(2026, 9, 1, 15),
        "ends_at": datetime(2026, 9, 1, 16),
    }

    assert CreateEventArgs(**schedule).notify_minutes_before == 15
    assert (
        CreateEventArgs(**schedule, notify_minutes_before=0).notify_minutes_before == 0
    )
    assert (
        CreateEventArgs(**schedule, notify_minutes_before=30).notify_minutes_before
        == 30
    )

    event_id = uuid4()
    assert (
        UpdateEventArgs(event_id=event_id, title="Keep").notify_minutes_before is None
    )
    assert (
        UpdateEventArgs(
            event_id=event_id,
            notify_minutes_before=0,
        ).notify_minutes_before
        == 0
    )
    assert (
        UpdateEventArgs(
            event_id=event_id,
            notify_minutes_before=30,
        ).notify_minutes_before
        == 30
    )
