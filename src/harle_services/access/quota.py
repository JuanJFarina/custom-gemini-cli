from collections.abc import MutableMapping, MutableSet
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TypeAlias
from uuid import UUID, uuid4

from harle_domain.conversations.ports import ConversationUsageRepository
from harle_services.messaging import UserWorkCoordinator
from harle_utils import Clock, as_utc, utc_now


@dataclass(frozen=True, slots=True)
class UtcMonthPeriod:
    starts_at: datetime
    resets_at: datetime


@dataclass(frozen=True, slots=True)
class QuotaReservation:
    id: UUID
    user_id: UUID
    remaining: int
    resets_at: datetime


@dataclass(frozen=True, slots=True)
class QuotaExceeded:
    remaining: int
    resets_at: datetime


QuotaResult: TypeAlias = QuotaReservation | QuotaExceeded


class UsageQuotaService:
    def __init__(
        self,
        conversations: ConversationUsageRepository,
        clock: Clock = utc_now,
    ) -> None:
        self._conversations = conversations
        self._clock = clock
        self._user_work = UserWorkCoordinator()
        self._reservations: MutableMapping[UUID, MutableSet[UUID]] = {}

    async def reserve(
        self,
        *,
        user_id: UUID,
        monthly_request_limit: int,
    ) -> QuotaResult:
        if monthly_request_limit <= 0:
            raise ValueError("Monthly request limit must be positive.")

        period = utc_month_period(self._clock())
        async with self._user_work.serialize(user_id):
            completed = await self._conversations.count_completed_conversations(
                user_id=user_id,
                created_from=period.starts_at,
                created_before=period.resets_at,
            )
            reservations = self._reservations.get(user_id)
            in_flight = len(reservations) if reservations is not None else 0
            available = monthly_request_limit - completed - in_flight
            if available <= 0:
                return QuotaExceeded(remaining=0, resets_at=period.resets_at)

            reservation_id = uuid4()
            if reservations is None:
                reservations = set()
                self._reservations[user_id] = reservations
            reservations.add(reservation_id)
            return QuotaReservation(
                id=reservation_id,
                user_id=user_id,
                remaining=available - 1,
                resets_at=period.resets_at,
            )

    async def release(self, reservation: QuotaReservation) -> None:
        async with self._user_work.serialize(reservation.user_id):
            reservations = self._reservations.get(reservation.user_id)
            if reservations is None:
                return
            reservations.discard(reservation.id)
            if not reservations:
                self._reservations.pop(reservation.user_id, None)


def utc_month_period(value: datetime) -> UtcMonthPeriod:
    current = as_utc(value)
    starts_at = current.replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    if starts_at.month == 12:
        resets_at = datetime(starts_at.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        resets_at = datetime(
            starts_at.year,
            starts_at.month + 1,
            1,
            tzinfo=timezone.utc,
        )
    return UtcMonthPeriod(starts_at=starts_at, resets_at=resets_at)
