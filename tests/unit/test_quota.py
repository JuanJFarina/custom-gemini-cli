import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from harle_services.access import (
    QuotaExceeded,
    QuotaReservation,
    UsageQuotaService,
)

NOW = datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc)


@dataclass
class FakeConversationUsage:
    completed: int
    created_from: datetime = NOW
    created_before: datetime = NOW

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


def test_quota_uses_plan_limit_and_explicit_utc_month_boundaries() -> None:
    conversations = FakeConversationUsage(completed=58)
    service = UsageQuotaService(conversations, clock=lambda: NOW)

    result = asyncio.run(
        service.reserve(user_id=uuid4(), monthly_request_limit=60),
    )

    assert isinstance(result, QuotaReservation)
    assert result.remaining == 1
    assert conversations.created_from == datetime(
        2026,
        12,
        1,
        tzinfo=timezone.utc,
    )
    assert conversations.created_before == datetime(
        2027,
        1,
        1,
        tzinfo=timezone.utc,
    )


def test_completed_conversations_at_plan_limit_are_rejected() -> None:
    service = UsageQuotaService(
        FakeConversationUsage(completed=60),
        clock=lambda: NOW,
    )

    result = asyncio.run(
        service.reserve(user_id=uuid4(), monthly_request_limit=60),
    )

    assert isinstance(result, QuotaExceeded)
    assert result.remaining == 0
    assert result.resets_at == datetime(2027, 1, 1, tzinfo=timezone.utc)


def test_concurrent_reservations_cannot_exceed_limit_and_release_restores_slot() -> None:
    async def exercise() -> None:
        user_id = uuid4()
        service = UsageQuotaService(
            FakeConversationUsage(completed=59),
            clock=lambda: NOW,
        )

        first, second = await asyncio.gather(
            service.reserve(user_id=user_id, monthly_request_limit=60),
            service.reserve(user_id=user_id, monthly_request_limit=60),
        )
        results = (first, second)
        reservations = [
            result for result in results if isinstance(result, QuotaReservation)
        ]
        rejections = [
            result for result in results if isinstance(result, QuotaExceeded)
        ]

        assert len(reservations) == 1
        assert len(rejections) == 1

        await service.release(reservations[0])
        retried = await service.reserve(
            user_id=user_id,
            monthly_request_limit=60,
        )
        assert isinstance(retried, QuotaReservation)

    asyncio.run(exercise())
