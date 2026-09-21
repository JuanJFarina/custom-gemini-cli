from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Protocol, runtime_checkable
from uuid import UUID

from .models import EventNotificationOccurrence, InteractionEvent, InternalEvent


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
        notification_grace_period: timedelta,
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


@runtime_checkable
class EventNotificationUsageRepository(Protocol):
    async def count_deliveries(
        self,
        *,
        user_id: UUID,
        delivered_from: datetime,
        delivered_before: datetime,
    ) -> int: ...

    async def was_delivered(
        self,
        *,
        occurrence: EventNotificationOccurrence,
    ) -> bool: ...

    async def record_delivery(
        self,
        *,
        occurrence: EventNotificationOccurrence,
        delivered_at: datetime,
    ) -> bool: ...

    async def claim_quota_notice(
        self,
        *,
        user_id: UUID,
        period_starts_at: datetime,
        attempted_at: datetime,
    ) -> bool: ...

    async def mark_quota_notice_delivered(
        self,
        *,
        user_id: UUID,
        period_starts_at: datetime,
        delivered_at: datetime,
    ) -> None: ...


@runtime_checkable
class InteractionEventRepository(Protocol):
    async def get_for_user(
        self,
        *,
        user_id: UUID,
    ) -> InteractionEvent | None: ...

    async def list_active(
        self,
        *,
        limit: int,
        user_message_from: datetime,
        current_time: datetime,
    ) -> Sequence[InteractionEvent]: ...

    async def disable(
        self,
        *,
        user_id: UUID,
        event_id: UUID,
        updated_at: datetime,
    ) -> InteractionEvent | None: ...

    async def enable(
        self,
        *,
        user_id: UUID,
        event_id: UUID,
        updated_at: datetime,
    ) -> InteractionEvent | None: ...

    async def record_user_message(
        self,
        *,
        user_id: UUID,
        update_ids: Sequence[int],
    ) -> InteractionEvent | None: ...

    async def record_agent_message(
        self,
        *,
        user_id: UUID,
        occurred_at: datetime,
    ) -> InteractionEvent | None: ...
