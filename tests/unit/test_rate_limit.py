from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from harle_services.access import (
    RateLimitAccepted,
    RateLimitService,
    TemporaryBan,
)

NOW = datetime(2026, 8, 31, tzinfo=timezone.utc)


@dataclass
class MutableClock:
    current: datetime

    def __call__(self) -> datetime:
        return self.current

    def advance(self, duration: timedelta) -> None:
        self.current += duration


def trigger_ban(service: RateLimitService, telegram_user_id: int) -> TemporaryBan:
    for _ in range(9):
        assert isinstance(service.check(telegram_user_id), RateLimitAccepted)
    result = service.check(telegram_user_id)
    assert isinstance(result, TemporaryBan)
    return result


def test_tenth_message_triggers_one_notice_per_cooldown() -> None:
    service = RateLimitService(clock=MutableClock(NOW))

    ban = trigger_ban(service, telegram_user_id=101)
    repeated = service.check(telegram_user_id=101)

    assert ban.blocked_until == NOW + timedelta(seconds=60)
    assert ban.notify_user
    assert isinstance(repeated, TemporaryBan)
    assert not repeated.notify_user


def test_ban_is_isolated_by_telegram_identity() -> None:
    service = RateLimitService(clock=MutableClock(NOW))

    trigger_ban(service, telegram_user_id=101)

    assert isinstance(service.check(202), RateLimitAccepted)


def test_cooldowns_escalate_and_strikes_decay_each_incident_free_hour() -> None:
    clock = MutableClock(NOW)
    service = RateLimitService(clock=clock)

    first = trigger_ban(service, telegram_user_id=101)
    clock.advance(timedelta(seconds=61))
    second_at = clock.current
    second = trigger_ban(service, telegram_user_id=101)
    clock.advance(timedelta(minutes=5, seconds=1))
    third_at = clock.current
    third = trigger_ban(service, telegram_user_id=101)
    clock.advance(timedelta(hours=3, seconds=1))
    decayed_at = clock.current
    decayed = trigger_ban(service, telegram_user_id=101)

    assert first.blocked_until == NOW + timedelta(seconds=60)
    assert second.blocked_until == second_at + timedelta(minutes=5)
    assert third.blocked_until == third_at + timedelta(hours=1)
    assert decayed.blocked_until == decayed_at + timedelta(seconds=60)
