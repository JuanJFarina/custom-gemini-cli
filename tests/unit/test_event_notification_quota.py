import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import pytest
from pytest import MonkeyPatch

import harle_services.events.notifications as notifications_module
from harle_domain.accounts import (
    ExternalIdentity,
    Plan,
    ResolvedUser,
    SubscriptionPeriod,
    SubscriptionStatus,
    User,
)
from harle_domain.events import (
    EventDetails,
    EventInterval,
    EventNotification,
    EventNotificationOccurrence,
    EventNotificationUsageRepository,
    EventStatus,
    EventTimestamps,
    EventType,
    InteractionEvent,
    InternalEvent,
)
from harle_domain.messaging import OutboundMessenger
from harle_domain.tools import HarleToolStore
from harle_services.access import PreflightService
from harle_services.events import (
    EventNotificationOutcome,
    EventNotificationQuotaService,
    EventNotificationService,
    InteractionEventService,
    NotificationQuotaExceeded,
    NotificationQuotaReservation,
)
from harle_services.runtime import UserRuntime, UserRuntimeFactory
from harle_utils import MessageDeliveryError

NOW = datetime(2026, 9, 17, 15, tzinfo=timezone.utc)
PERIOD = SubscriptionPeriod(
    datetime(2026, 9, 1, tzinfo=timezone.utc),
    datetime(2026, 10, 1, tzinfo=timezone.utc),
)


@dataclass(frozen=True, slots=True)
class StoredDelivery:
    occurrence: EventNotificationOccurrence
    delivered_at: datetime


@dataclass(frozen=True, slots=True)
class StoredNotice:
    user_id: UUID
    period_starts_at: datetime


class FakeUsageRepository:
    def __init__(self) -> None:
        self.deliveries: list[StoredDelivery] = []
        self.notices: set[StoredNotice] = set()

    async def count_deliveries(
        self,
        *,
        user_id: UUID,
        delivered_from: datetime,
        delivered_before: datetime,
    ) -> int:
        return sum(
            delivery.occurrence.user_id == user_id
            and delivered_from <= delivery.delivered_at < delivered_before
            for delivery in self.deliveries
        )

    async def was_delivered(
        self,
        *,
        occurrence: EventNotificationOccurrence,
    ) -> bool:
        return any(delivery.occurrence == occurrence for delivery in self.deliveries)

    async def record_delivery(
        self,
        *,
        occurrence: EventNotificationOccurrence,
        delivered_at: datetime,
    ) -> bool:
        if await self.was_delivered(occurrence=occurrence):
            return False
        self.deliveries.append(StoredDelivery(occurrence, delivered_at))
        return True

    async def claim_quota_notice(
        self,
        *,
        user_id: UUID,
        period_starts_at: datetime,
        attempted_at: datetime,
    ) -> bool:
        del attempted_at
        notice = StoredNotice(user_id, period_starts_at)
        if notice in self.notices:
            return False
        self.notices.add(notice)
        return True

    async def mark_quota_notice_delivered(
        self,
        *,
        user_id: UUID,
        period_starts_at: datetime,
        delivered_at: datetime,
    ) -> None:
        del delivered_at
        if StoredNotice(user_id, period_starts_at) not in self.notices:
            raise RuntimeError


class FakePreflight:
    def __init__(self, user: ResolvedUser) -> None:
        self.user = user

    async def resolve_active_user(self, user_id: UUID) -> ResolvedUser:
        if user_id != self.user.user.id:
            raise RuntimeError
        return self.user


class FakeUsers:
    async def create_for_resolved_user(
        self,
        *,
        resolved_user: ResolvedUser,
        telegram_chat_id: int,
    ) -> UserRuntime:
        del resolved_user, telegram_chat_id
        return cast(
            UserRuntime,
            SimpleNamespace(
                user_profile=SimpleNamespace(locale="en-US", timezone="UTC"),
            ),
        )


class FakeMessenger:
    def __init__(self, *, fails: bool = False) -> None:
        self.fails = fails
        self.messages: list[str] = []

    async def send_message(self, *, chat_id: int, text: str) -> None:
        del chat_id
        if self.fails:
            raise MessageDeliveryError
        self.messages.append(text)


class FakeInteractions:
    def __init__(self) -> None:
        self.agent_messages: list[UUID] = []

    async def record_agent_message(self, *, user_id: UUID) -> object:
        self.agent_messages.append(user_id)
        return object()


class FakeGeneratedHarle:
    def __init__(self) -> None:
        self.saved = False

    async def save_scheduled(self, **_: object) -> None:
        self.saved = True


def _event(
    user_id: UUID,
    *,
    starts_at: datetime,
    event_id: UUID | None = None,
    notify_before: timedelta = timedelta(minutes=15),
) -> InternalEvent:
    return InternalEvent(
        id=event_id or uuid4(),
        user_id=user_id,
        details=EventDetails(
            title="Reminder",
            description="Test",
            interval=EventInterval(
                starts_at=starts_at,
                ends_at=starts_at + timedelta(hours=1),
                timezone="UTC",
                all_day=False,
            ),
            event_type=EventType.USER_EVENT,
            status=EventStatus.ACTIVE,
        ),
        notification=EventNotification(
            window_start=starts_at - notify_before,
        ),
        timestamps=EventTimestamps(created_at=NOW, updated_at=NOW),
    )


def _resolved_user(user_id: UUID, *, limit: int) -> ResolvedUser:
    plan = Plan(
        code="free",
        monthly_request_limit=60,
        monthly_notification_limit=limit,
        active=True,
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
            subscription_period=SubscriptionPeriod(
                datetime(2026, 9, 1, tzinfo=timezone.utc),
                datetime(2026, 10, 1, tzinfo=timezone.utc),
            ),
            created_at=NOW,
            updated_at=NOW,
        ),
        plan=plan,
        identity=ExternalIdentity(
            id=uuid4(),
            user_id=user_id,
            provider="telegram",
            external_user_id="123",
            display_name="User",
            created_at=NOW,
            updated_at=NOW,
        ),
    )


def _notification_service(
    user: ResolvedUser,
    usage: FakeUsageRepository,
    messenger: FakeMessenger,
) -> EventNotificationService:
    return EventNotificationService(
        preflight=cast(PreflightService, FakePreflight(user)),
        users=cast(UserRuntimeFactory, FakeUsers()),
        messenger=cast(OutboundMessenger, messenger),
        quotas=EventNotificationQuotaService(
            cast(EventNotificationUsageRepository, usage),
            clock=lambda: NOW,
        ),
        interactions=cast(InteractionEventService, FakeInteractions()),
        tool_store_builder=lambda _user, _timezone: HarleToolStore(),
    )


def test_notification_quota_reserves_counts_and_blocks() -> None:
    async def verify() -> None:
        user_id = uuid4()
        usage = FakeUsageRepository()
        service = EventNotificationQuotaService(
            cast(EventNotificationUsageRepository, usage),
            clock=lambda: NOW,
        )
        first = await service.reserve(
            event=_event(
                user_id,
                starts_at=NOW + timedelta(hours=1),
                notify_before=timedelta(0),
            ),
            monthly_limit=1,
            period=PERIOD,
        )
        assert isinstance(first, NotificationQuotaReservation)
        assert (
            await service.status(
                user_id=user_id,
                monthly_limit=1,
                period=PERIOD,
            )
        ).remaining == 0
        assert await service.complete(first)

        blocked = await service.reserve(
            event=_event(user_id, starts_at=NOW + timedelta(hours=2)),
            monthly_limit=1,
            period=PERIOD,
        )
        assert isinstance(blocked, NotificationQuotaExceeded)
        assert await service.claim_exhaustion_notice(blocked)
        assert not await service.claim_exhaustion_notice(blocked)

    asyncio.run(verify())


def test_exhausted_quota_skips_gemini_and_sends_one_notice(
    monkeypatch: MonkeyPatch,
) -> None:
    async def verify() -> None:
        user_id = uuid4()
        usage = FakeUsageRepository()
        existing = _event(user_id, starts_at=NOW + timedelta(minutes=30))
        await usage.record_delivery(
            occurrence=EventNotificationOccurrence(
                event_id=existing.id,
                user_id=user_id,
                starts_at=existing.starts_at,
                window_start=existing.notification_window_start,
            ),
            delivered_at=NOW,
        )
        messenger = FakeMessenger()
        service = _notification_service(
            _resolved_user(user_id, limit=1),
            usage,
            messenger,
        )

        async def fail_generation(**_: object) -> object:
            raise AssertionError("Gemini must not run after quota exhaustion.")

        monkeypatch.setattr(
            notifications_module,
            "generate_response",
            fail_generation,
        )
        event = _event(user_id, starts_at=NOW + timedelta(hours=1))

        assert await service.notify(event) is EventNotificationOutcome.QUOTA_EXCEEDED
        assert await service.notify(event) is EventNotificationOutcome.QUOTA_EXCEEDED
        assert len(messenger.messages) == 1
        assert "limit of 1" in messenger.messages[0]

    asyncio.run(verify())


def test_failed_delivery_releases_quota_without_consuming_it(
    monkeypatch: MonkeyPatch,
) -> None:
    async def verify() -> None:
        user_id = uuid4()
        usage = FakeUsageRepository()
        messenger = FakeMessenger(fails=True)
        service = _notification_service(
            _resolved_user(user_id, limit=1),
            usage,
            messenger,
        )

        async def generate(**_: object) -> object:
            return SimpleNamespace(result=SimpleNamespace(response_text="Reminder"))

        monkeypatch.setattr(notifications_module, "generate_response", generate)
        with pytest.raises(MessageDeliveryError):
            await service.notify(
                _event(user_id, starts_at=NOW + timedelta(hours=1)),
            )

        assert not usage.deliveries
        assert (
            await service.quotas.status(
                user_id=user_id,
                monthly_limit=1,
                period=PERIOD,
            )
        ).remaining == 1

    asyncio.run(verify())


def test_successful_notification_persists_scheduled_message(
    monkeypatch: MonkeyPatch,
) -> None:
    async def verify() -> None:
        user_id = uuid4()
        usage = FakeUsageRepository()
        messenger = FakeMessenger()
        service = _notification_service(
            _resolved_user(user_id, limit=1),
            usage,
            messenger,
        )
        harle = FakeGeneratedHarle()

        async def generate(**_: object) -> object:
            return SimpleNamespace(
                harle=harle,
                result=SimpleNamespace(response_text="Reminder"),
            )

        monkeypatch.setattr(notifications_module, "generate_response", generate)
        outcome = await service.notify(
            _event(user_id, starts_at=NOW + timedelta(hours=1)),
        )

        assert outcome is EventNotificationOutcome.DELIVERED
        assert messenger.messages == ["Reminder"]
        assert harle.saved
        assert len(usage.deliveries) == 1
        interactions = cast(FakeInteractions, service.interactions)
        assert interactions.agent_messages == [user_id]

    asyncio.run(verify())


def test_interaction_notification_persists_without_quota(
    monkeypatch: MonkeyPatch,
) -> None:
    async def verify() -> None:
        user_id = uuid4()
        usage = FakeUsageRepository()
        messenger = FakeMessenger()
        service = _notification_service(
            _resolved_user(user_id, limit=1),
            usage,
            messenger,
        )
        harle = FakeGeneratedHarle()

        async def generate(**_: object) -> object:
            return SimpleNamespace(
                harle=harle,
                result=SimpleNamespace(response_text="How are you?"),
            )

        monkeypatch.setattr(notifications_module, "generate_response", generate)
        outcome = await service.notify_interaction(
            InteractionEvent(
                id=uuid4(),
                user_id=user_id,
                status=EventStatus.ACTIVE,
                last_user_message_at=NOW,
                last_agent_message_at=None,
                created_at=NOW,
                updated_at=NOW,
            ),
        )

        assert outcome is EventNotificationOutcome.DELIVERED
        assert messenger.messages == ["How are you?"]
        assert harle.saved
        assert not usage.deliveries

    asyncio.run(verify())
