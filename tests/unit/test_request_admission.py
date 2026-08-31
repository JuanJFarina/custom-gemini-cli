import asyncio
from datetime import datetime, timezone
from typing import cast
from uuid import uuid4

import pytest

from harle_domain.accounts import ResolvedUser
from harle_services.access import (
    PreflightAccepted,
    PreflightService,
    QuotaReservation,
    UsageQuotaService,
)
from harle_services.runtime import RequestAdmissionService, UserRuntimeFactory
from harle_utils import MissingProfileError


class FakePreflight:
    def __init__(self, result: PreflightAccepted) -> None:
        self.result = result

    async def check(self, telegram_user_id: int) -> PreflightAccepted:
        del telegram_user_id
        return self.result


class FailingUsers:
    async def create_for_resolved_user(
        self,
        *,
        resolved_user: ResolvedUser,
        telegram_chat_id: int,
        telegram_update_id: int,
    ) -> None:
        del resolved_user, telegram_chat_id, telegram_update_id
        raise MissingProfileError


class FakeQuota:
    def __init__(self) -> None:
        self.released: list[QuotaReservation] = []

    async def release(self, reservation: QuotaReservation) -> None:
        self.released.append(reservation)


def test_runtime_creation_failure_releases_quota_reservation() -> None:
    async def exercise() -> None:
        user_id = uuid4()
        reservation = QuotaReservation(
            id=uuid4(),
            user_id=user_id,
            remaining=1,
            resets_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        )
        preflight = FakePreflight(
            PreflightAccepted(
                resolved_user=cast(ResolvedUser, object()),
                quota_reservation=reservation,
            ),
        )
        quota = FakeQuota()
        service = RequestAdmissionService(
            preflight=cast(PreflightService, preflight),
            users=cast(UserRuntimeFactory, FailingUsers()),
            quota=cast(UsageQuotaService, quota),
        )

        with pytest.raises(MissingProfileError):
            await service.admit(
                telegram_user_id=1,
                telegram_chat_id=2,
                telegram_update_id=3,
            )

        assert quota.released == [reservation]

    asyncio.run(exercise())
