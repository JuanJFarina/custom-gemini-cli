from collections import deque
from collections.abc import MutableMapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TypeAlias

from harle_utils import Clock, as_utc, utc_now

ROLLING_WINDOW = timedelta(seconds=2)
MESSAGES_BEFORE_BAN = 10
STRIKE_DECAY_INTERVAL = timedelta(hours=1)
BAN_COOLDOWNS: Sequence[timedelta] = (
    timedelta(seconds=60),
    timedelta(minutes=5),
    timedelta(hours=1),
)


@dataclass(frozen=True, slots=True)
class RateLimitAccepted:
    pass


@dataclass(frozen=True, slots=True)
class TemporaryBan:
    blocked_until: datetime
    notify_user: bool


RateLimitResult: TypeAlias = RateLimitAccepted | TemporaryBan


@dataclass(slots=True)
class _IdentityRateLimit:
    timestamps: deque[datetime] = field(default_factory=deque)
    blocked_until: datetime | None = None
    strikes: int = 0
    decay_anchor: datetime | None = None
    notice_sent: bool = False


class RateLimitService:
    def __init__(self, clock: Clock = utc_now) -> None:
        self._clock = clock
        self._identities: MutableMapping[int, _IdentityRateLimit] = {}

    def check(self, telegram_user_id: int) -> RateLimitResult:
        if telegram_user_id <= 0:
            raise ValueError("Telegram user identifier must be positive.")

        now = as_utc(self._clock())
        state = self._identities.setdefault(
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
            return RateLimitAccepted()

        state.timestamps.clear()
        state.strikes = min(state.strikes + 1, len(BAN_COOLDOWNS))
        state.decay_anchor = now
        state.blocked_until = now + BAN_COOLDOWNS[state.strikes - 1]
        state.notice_sent = True
        return TemporaryBan(state.blocked_until, notify_user=True)


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
