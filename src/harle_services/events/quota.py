from collections.abc import MutableMapping, MutableSet
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TypeAlias
from uuid import UUID

from harle_domain.accounts import SubscriptionPeriod
from harle_domain.events import (
    EventNotificationOccurrence,
    EventNotificationUsageRepository,
    InternalEvent,
)
from harle_utils import Clock, as_utc, utc_now


@dataclass(frozen=True, slots=True)
class NotificationQuotaStatus:
    limit: int
    remaining: int
    resets_at: datetime


@dataclass(frozen=True, slots=True)
class NotificationQuotaReservation:
    occurrence: EventNotificationOccurrence
    remaining: int
    resets_at: datetime


@dataclass(frozen=True, slots=True)
class NotificationQuotaExceeded:
    user_id: UUID
    limit: int
    period_starts_at: datetime
    resets_at: datetime


class NotificationQuotaSkip(str, Enum):
    ALREADY_DELIVERED = "already_delivered"
    ALREADY_IN_FLIGHT = "already_in_flight"


NotificationQuotaAdmission: TypeAlias = (
    NotificationQuotaReservation | NotificationQuotaExceeded | NotificationQuotaSkip
)


class EventNotificationQuotaService:
    def __init__(
        self,
        repository: EventNotificationUsageRepository,
        clock: Clock = utc_now,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._reservations: MutableMapping[
            UUID,
            MutableSet[EventNotificationOccurrence],
        ] = {}

    async def status(
        self,
        *,
        user_id: UUID,
        monthly_limit: int,
        period: SubscriptionPeriod,
    ) -> NotificationQuotaStatus:
        _require_positive_limit(monthly_limit)
        delivered = await self._repository.count_deliveries(
            user_id=user_id,
            delivered_from=period.starts_at,
            delivered_before=period.ends_at,
        )
        in_flight = len(self._reservations.get(user_id, set()))
        return NotificationQuotaStatus(
            limit=monthly_limit,
            remaining=max(0, monthly_limit - delivered - in_flight),
            resets_at=period.ends_at,
        )

    async def reserve(
        self,
        *,
        event: InternalEvent,
        monthly_limit: int,
        period: SubscriptionPeriod,
    ) -> NotificationQuotaAdmission:
        _require_positive_limit(monthly_limit)
        occurrence = _notification_occurrence(event)
        if await self._repository.was_delivered(occurrence=occurrence):
            return NotificationQuotaSkip.ALREADY_DELIVERED

        reservations = self._reservations.get(event.user_id)
        if reservations is not None and occurrence in reservations:
            return NotificationQuotaSkip.ALREADY_IN_FLIGHT

        delivered = await self._repository.count_deliveries(
            user_id=event.user_id,
            delivered_from=period.starts_at,
            delivered_before=period.ends_at,
        )
        in_flight = len(reservations) if reservations is not None else 0
        available = monthly_limit - delivered - in_flight
        if available <= 0:
            return NotificationQuotaExceeded(
                user_id=event.user_id,
                limit=monthly_limit,
                period_starts_at=period.starts_at,
                resets_at=period.ends_at,
            )

        reservation = NotificationQuotaReservation(
            occurrence=occurrence,
            remaining=available - 1,
            resets_at=period.ends_at,
        )
        if reservations is None:
            reservations = set()
            self._reservations[event.user_id] = reservations
        reservations.add(occurrence)
        return reservation

    async def complete(
        self,
        reservation: NotificationQuotaReservation,
    ) -> bool:
        reservations = self._reservations.get(reservation.occurrence.user_id)
        if reservations is None or reservation.occurrence not in reservations:
            raise ValueError("Notification quota reservation is not active.")
        try:
            return await self._repository.record_delivery(
                occurrence=reservation.occurrence,
                delivered_at=as_utc(self._clock()),
            )
        finally:
            self.release(reservation)

    def release(
        self,
        reservation: NotificationQuotaReservation,
    ) -> None:
        user_id = reservation.occurrence.user_id
        reservations = self._reservations.get(user_id)
        if reservations is None:
            return
        reservations.discard(reservation.occurrence)
        if not reservations:
            self._reservations.pop(user_id)

    async def claim_exhaustion_notice(
        self,
        exceeded: NotificationQuotaExceeded,
    ) -> bool:
        return await self._repository.claim_quota_notice(
            user_id=exceeded.user_id,
            period_starts_at=exceeded.period_starts_at,
            attempted_at=as_utc(self._clock()),
        )

    async def mark_exhaustion_notice_delivered(
        self,
        exceeded: NotificationQuotaExceeded,
    ) -> None:
        await self._repository.mark_quota_notice_delivered(
            user_id=exceeded.user_id,
            period_starts_at=exceeded.period_starts_at,
            delivered_at=as_utc(self._clock()),
        )


def _notification_occurrence(
    event: InternalEvent,
) -> EventNotificationOccurrence:
    return EventNotificationOccurrence(
        event_id=event.id,
        user_id=event.user_id,
        starts_at=event.starts_at,
        window_start=event.notification_window_start,
    )


def _require_positive_limit(value: int) -> None:
    if isinstance(value, bool) or value <= 0:
        raise ValueError("Monthly notification limit must be positive.")
