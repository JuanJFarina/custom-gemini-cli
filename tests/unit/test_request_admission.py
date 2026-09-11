import asyncio
from collections.abc import Mapping
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from harle_domain.accounts import (
    AccountRepository,
    ExternalIdentity,
    Plan,
    ResolvedUser,
    SubscriptionStatus,
    User,
)
from harle_services.access import (
    PreflightAccepted,
    PreflightService,
    QuotaExceeded,
    QuotaReservation,
    TemporaryBan,
)
from harle_utils import InactiveSubscriptionError, UnknownIdentityError

NOW = datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc)


class FakeAccounts(AccountRepository):
    def __init__(self, users: Mapping[int, ResolvedUser]) -> None:
        self.users = users

    async def resolve_telegram_identity(
        self,
        *,
        telegram_user_id: int,
    ) -> ResolvedUser | None:
        return self.users.get(telegram_user_id)


class FakeConversationUsage:
    def __init__(self, completed: int) -> None:
        self.completed = completed
        self.created_from = NOW
        self.created_before = NOW

    async def count_completed_conversations(
        self,
        *,
        user_id: UUID,
        created_from: datetime,
        created_before: datetime,
    ) -> int:
        del user_id
        self.created_from = created_from
        self.created_before = created_before
        return self.completed


def resolved_user(*, active: bool = True) -> ResolvedUser:
    user_id = uuid4()
    plan = Plan(
        code="basic",
        monthly_request_limit=60,
        active=active,
        created_at=NOW,
        updated_at=NOW,
    )
    return ResolvedUser(
        user=User(
            id=user_id,
            display_name="User",
            plan_code=plan.code,
            subscription_status=SubscriptionStatus.ACTIVE,
            subscription_valid_until=None,
            subscription_synced_at=NOW,
            created_at=NOW,
            updated_at=NOW,
        ),
        plan=plan,
        identity=ExternalIdentity(
            id=uuid4(),
            user_id=user_id,
            provider="telegram",
            external_user_id="1",
            display_name="User",
            created_at=NOW,
            updated_at=NOW,
        ),
    )


def test_preflight_resolves_access_and_reserves_monthly_quota() -> None:
    user = resolved_user()
    usage = FakeConversationUsage(completed=58)
    service = PreflightService(
        FakeAccounts({1: user}),
        usage,
        clock=lambda: NOW,
    )

    result = asyncio.run(service.check(1))

    assert isinstance(result, PreflightAccepted)
    assert result.resolved_user is user
    assert result.quota_reservation.remaining == 1
    assert usage.created_from == datetime(2026, 12, 1, tzinfo=timezone.utc)
    assert usage.created_before == datetime(2027, 1, 1, tzinfo=timezone.utc)


def test_preflight_rejects_unknown_inactive_and_over_quota_users() -> None:
    async def verify() -> None:
        inactive = resolved_user(active=False)
        service = PreflightService(
            FakeAccounts({2: inactive}),
            FakeConversationUsage(completed=60),
            clock=lambda: NOW,
        )

        with pytest.raises(UnknownIdentityError):
            await service.check(1)
        with pytest.raises(InactiveSubscriptionError):
            await service.check(2)

        active = resolved_user()
        limited = PreflightService(
            FakeAccounts({3: active}),
            FakeConversationUsage(completed=60),
            clock=lambda: NOW,
        )
        assert isinstance(await limited.check(3), QuotaExceeded)

        rapid = PreflightService(
            FakeAccounts({4: active}),
            FakeConversationUsage(completed=0),
            clock=lambda: NOW,
        )
        results = [rapid.check_rate_limit(4) for _ in range(10)]
        assert isinstance(results[-1], TemporaryBan)

    asyncio.run(verify())


def test_preflight_releases_in_flight_quota_reservations() -> None:
    async def verify() -> None:
        user = resolved_user()
        service = PreflightService(
            FakeAccounts({1: user}),
            FakeConversationUsage(completed=59),
            clock=lambda: NOW,
        )

        first = await service.check(1)
        second = await service.check(1)
        assert isinstance(first, PreflightAccepted)
        assert isinstance(second, QuotaExceeded)

        reservation: QuotaReservation = first.quota_reservation
        await service.release(reservation)
        assert isinstance(await service.check(1), PreflightAccepted)

    asyncio.run(verify())
