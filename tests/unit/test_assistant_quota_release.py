import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from pytest import MonkeyPatch

import harle_api.assistant as assistant_module
from harle_api.telegram import IncomingTelegramMessage
from harle_services.access import QuotaReservation, UsageQuotaService
from harle_services.messaging import UserWorkCoordinator
from harle_services.runtime import UserRuntime


class FakeQuota:
    def __init__(self) -> None:
        self.released: list[QuotaReservation] = []

    async def release(self, reservation: QuotaReservation) -> None:
        self.released.append(reservation)


def test_message_processing_releases_quota_on_success_and_failure(
    monkeypatch: MonkeyPatch,
) -> None:
    async def exercise() -> None:
        user_id = uuid4()
        user_runtime = cast(
            UserRuntime,
            SimpleNamespace(
                resolved_user=SimpleNamespace(
                    user=SimpleNamespace(id=user_id),
                ),
            ),
        )
        quota = FakeQuota()
        calls = 0

        async def fake_process(**_: object) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("failed")

        monkeypatch.setattr(
            assistant_module,
            "_process_telegram_message",
            fake_process,
        )
        reservations = [
            QuotaReservation(
                id=uuid4(),
                user_id=user_id,
                remaining=1,
                resets_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
            )
            for _ in range(2)
        ]
        message = IncomingTelegramMessage(
            update_id=1,
            chat_id=2,
            user_id=3,
            user_name="User",
            text="Hello",
        )

        await assistant_module.process_telegram_message(
            message=message,
            user_runtime=user_runtime,
            user_work=UserWorkCoordinator(),
            usage_quota=cast(UsageQuotaService, quota),
            quota_reservation=reservations[0],
        )
        with pytest.raises(RuntimeError, match="failed"):
            await assistant_module.process_telegram_message(
                message=message,
                user_runtime=user_runtime,
                user_work=UserWorkCoordinator(),
                usage_quota=cast(UsageQuotaService, quota),
                quota_reservation=reservations[1],
            )

        assert quota.released == reservations

    asyncio.run(exercise())
