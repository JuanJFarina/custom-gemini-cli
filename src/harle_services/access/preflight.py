from asyncio import Lock
from collections import deque
from collections.abc import MutableMapping, MutableSet, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TypeAlias
from uuid import UUID, uuid4

from harle_domain.accounts import (
    AccountRepository,
    ResolvedUser,
    SubscriptionStatus,
)
from harle_domain.conversations.ports import ConversationUsageRepository
from harle_utils import (
    Clock,
    InactiveSubscriptionError,
    UnknownIdentityError,
    as_utc,
    utc_now,
)

ROLLING_WINDOW = timedelta(seconds=2)
MESSAGES_BEFORE_BAN = 10
STRIKE_DECAY_INTERVAL = timedelta(hours=1)
BAN_COOLDOWNS: Sequence[timedelta] = (
    timedelta(seconds=60),
    timedelta(minutes=5),
    timedelta(hours=1),
)


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


@dataclass(frozen=True, slots=True)
class TemporaryBan:
    blocked_until: datetime
    notify_user: bool


@dataclass(frozen=True, slots=True)
class PreflightAccepted:
    resolved_user: ResolvedUser
    quota_reservation: QuotaReservation


PreflightResult: TypeAlias = PreflightAccepted | QuotaExceeded


class PreflightService:
    def __init__(
        self,
        accounts: AccountRepository,
        conversations: ConversationUsageRepository,
        clock: Clock = utc_now,
    ) -> None:
        self._accounts = accounts
        self._conversations = conversations
        self._clock = clock
        self._rate_limits: MutableMapping[int, _IdentityRateLimit] = {}
        self._quota_locks: MutableMapping[UUID, Lock] = {}
        self._reservations: MutableMapping[UUID, MutableSet[UUID]] = {}

    async def check(self, telegram_user_id: int) -> PreflightResult:
        resolved_user = await self._accounts.resolve_telegram_identity(
            telegram_user_id=telegram_user_id,
        )
        if resolved_user is None:
            raise UnknownIdentityError

        _require_active_subscription(resolved_user, as_utc(self._clock()))
        quota = await self._reserve_quota(
            user_id=resolved_user.user.id,
            monthly_request_limit=resolved_user.plan.monthly_request_limit,
        )
        if isinstance(quota, QuotaExceeded):
            return quota
        return PreflightAccepted(
            resolved_user=resolved_user,
            quota_reservation=quota,
        )

    async def release(self, reservation: QuotaReservation) -> None:
        async with self._quota_lock(reservation.user_id):
            reservations = self._reservations.get(reservation.user_id)
            if reservations is None:
                return
            reservations.discard(reservation.id)
            if not reservations:
                self._reservations.pop(reservation.user_id, None)

    def check_rate_limit(self, telegram_user_id: int) -> TemporaryBan | None:
        if telegram_user_id <= 0:
            raise ValueError("Telegram user identifier must be positive.")

        now = as_utc(self._clock())
        state = self._rate_limits.setdefault(
            telegram_user_id,
            _IdentityRateLimit(),
        )
        _decay_strikes(state, now)

        if state.blocked_until is not None and now < state.blocked_until:
            notify_user = not state.notice_sent
            state.notice_sent = True
            return TemporaryBan(state.blocked_until, notify_user)

        state.blocked_until = None
        state.notice_sent = False
        cutoff = now - ROLLING_WINDOW
        while state.timestamps and state.timestamps[0] <= cutoff:
            state.timestamps.popleft()
        state.timestamps.append(now)

        if len(state.timestamps) < MESSAGES_BEFORE_BAN:
            return None

        state.timestamps.clear()
        state.strikes = min(state.strikes + 1, len(BAN_COOLDOWNS))
        state.decay_anchor = now
        state.blocked_until = now + BAN_COOLDOWNS[state.strikes - 1]
        state.notice_sent = True
        return TemporaryBan(state.blocked_until, notify_user=True)

    async def _reserve_quota(
        self,
        *,
        user_id: UUID,
        monthly_request_limit: int,
    ) -> QuotaReservation | QuotaExceeded:
        if monthly_request_limit <= 0:
            raise ValueError("Monthly request limit must be positive.")

        period = utc_month_period(self._clock())
        async with self._quota_lock(user_id):
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

    def _quota_lock(self, user_id: UUID) -> Lock:
        return self._quota_locks.setdefault(user_id, Lock())


@dataclass(slots=True)
class _IdentityRateLimit:
    timestamps: deque[datetime] = field(default_factory=deque)
    blocked_until: datetime | None = None
    strikes: int = 0
    decay_anchor: datetime | None = None
    notice_sent: bool = False


def _require_active_subscription(
    resolved_user: ResolvedUser,
    current_time: datetime,
) -> None:
    user = resolved_user.user
    valid_until = user.subscription_valid_until
    is_expired = valid_until is not None and valid_until <= current_time
    if (
        not resolved_user.plan.active
        or user.subscription_status is not SubscriptionStatus.ACTIVE
        or is_expired
    ):
        raise InactiveSubscriptionError


def _decay_strikes(state: _IdentityRateLimit, now: datetime) -> None:
    if state.strikes == 0 or state.decay_anchor is None:
        return

    elapsed_intervals = int((now - state.decay_anchor) // STRIKE_DECAY_INTERVAL)
    if elapsed_intervals <= 0:
        return

    state.strikes = max(0, state.strikes - elapsed_intervals)
    if state.strikes == 0:
        state.decay_anchor = None
        return
    state.decay_anchor += STRIKE_DECAY_INTERVAL * elapsed_intervals


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
