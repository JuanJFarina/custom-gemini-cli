import asyncio
from collections.abc import MutableMapping, Sequence
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from harle_domain.events import (
    EventStatus,
    InternalEvent,
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
                or (
                    include_cancelled
                    and event.status is EventStatus.CANCELLED
                )
            )
        ]

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

    async def delete(
        self,
        *,
        user_id: UUID,
        event_id: UUID,
        deleted_at: datetime,
    ) -> InternalEvent | None:
        current = self.events.get(event_id)
        if (
            current is None
            or current.user_id != user_id
            or current.status is EventStatus.DELETED
        ):
            return None
        deleted = replace(
            current,
            details=replace(current.details, status=EventStatus.DELETED),
            timestamps=replace(
                current.timestamps,
                updated_at=deleted_at,
                deleted_at=deleted_at,
            ),
        )
        self.events[event_id] = deleted
        return deleted


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


def test_event_service_isolates_and_soft_deletes_events() -> None:
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

        assert await service.update(
            user_id=other_id,
            event_id=event.id,
            changes=UpdateEvent(title="Changed"),
        ) is None
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
        assert deleted.status is EventStatus.DELETED
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
