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
        include_cancelled: bool = False,
    ) -> InternalEvent | None: ...

    async def list_for_range(
        self,
        *,
        user_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
        include_cancelled: bool = False,
    ) -> Sequence[InternalEvent]: ...

    async def update(
        self,
        *,
        user_id: UUID,
        event: InternalEvent,
    ) -> InternalEvent | None: ...

    async def cancel(
        self,
        *,
        user_id: UUID,
        event_id: UUID,
        cancelled_at: datetime,
    ) -> InternalEvent | None: ...

    async def delete(
        self,
        *,
        user_id: UUID,
        event_id: UUID,
        deleted_at: datetime,
    ) -> InternalEvent | None: ...
