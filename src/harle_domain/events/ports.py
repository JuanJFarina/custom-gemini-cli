from collections.abc import Sequence
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from .models import InternalEvent


@runtime_checkable
class EventRepository(Protocol):
    async def create(
        self,
        *,
        user_id: UUID,
        event: InternalEvent,
    ) -> InternalEvent: ...

    async def get(
        self,
        *,
        user_id: UUID,
        event_id: UUID,
        include_disabled: bool = False,
    ) -> InternalEvent | None: ...

    async def list_for_range(
        self,
        *,
        user_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
        include_disabled: bool = False,
    ) -> Sequence[InternalEvent]: ...

    async def list_due_for_notification(
        self,
        *,
        current_time: datetime,
        limit: int,
    ) -> Sequence[InternalEvent]: ...

    async def update(
        self,
        *,
        user_id: UUID,
        event: InternalEvent,
    ) -> InternalEvent | None: ...

    async def disable(
        self,
        *,
        user_id: UUID,
        event_id: UUID,
        updated_at: datetime,
    ) -> InternalEvent | None: ...

    async def enable(
        self,
        *,
        user_id: UUID,
        event_id: UUID,
        updated_at: datetime,
    ) -> InternalEvent | None: ...

    async def mark_notification_delivered(
        self,
        *,
        user_id: UUID,
        event_id: UUID,
        expected_updated_at: datetime,
        updated_at: datetime,
    ) -> InternalEvent | None: ...

    async def delete(
        self,
        *,
        user_id: UUID,
        event_id: UUID,
    ) -> InternalEvent | None: ...
