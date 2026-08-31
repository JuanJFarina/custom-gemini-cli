from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from harle_domain.accounts.models import (
    ExternalIdentity,
    Plan,
    ResolvedUser,
    SubscriptionStatus,
    User,
)
from harle_services.access.subscriptions import SubscriptionService
from harle_utils import InactiveSubscriptionError

NOW = datetime(2026, 8, 31, tzinfo=timezone.utc)


def resolved_user(
    *,
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE,
    plan_active: bool = True,
    valid_until: datetime | None = None,
) -> ResolvedUser:
    user_id = uuid4()
    plan = Plan(
        code="basic",
        monthly_request_limit=480,
        active=plan_active,
        created_at=NOW,
        updated_at=NOW,
    )
    user = User(
        id=user_id,
        display_name="Beta User",
        plan_code=plan.code,
        subscription_status=status,
        subscription_valid_until=valid_until,
        subscription_synced_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    identity = ExternalIdentity(
        id=uuid4(),
        user_id=user_id,
        provider="telegram",
        external_user_id="123",
        display_name=user.display_name,
        created_at=NOW,
        updated_at=NOW,
    )
    return ResolvedUser(user=user, plan=plan, identity=identity)


def test_active_subscription_is_accepted() -> None:
    service = SubscriptionService(clock=lambda: NOW)

    assert service.require_active(resolved_user()).user.display_name == "Beta User"


def test_inactive_subscription_is_rejected() -> None:
    service = SubscriptionService(clock=lambda: NOW)
    candidates = [
        resolved_user(status=SubscriptionStatus.INACTIVE),
        resolved_user(plan_active=False),
        resolved_user(valid_until=NOW - timedelta(seconds=1)),
    ]

    for candidate in candidates:
        with pytest.raises(InactiveSubscriptionError):
            service.require_active(candidate)
