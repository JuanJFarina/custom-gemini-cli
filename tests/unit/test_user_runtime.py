import asyncio
from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal
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
from harle_domain.profiles import AssistantProfile, UserProfile
from harle_domain.tools.models import InternalToolCallInteraction
from harle_services.access import IdentityService, SubscriptionService
from harle_services.runtime import UserRuntimeFactory
from harle_utils import UnknownIdentityError

NOW = datetime(2026, 8, 31, tzinfo=timezone.utc)


class FakeAccounts(AccountRepository):
    def __init__(self, users: Mapping[int, ResolvedUser]) -> None:
        self.users = users

    async def resolve_telegram_identity(
        self,
        *,
        telegram_user_id: int,
    ) -> ResolvedUser | None:
        return self.users.get(telegram_user_id)


class FakeUserProfiles:
    def __init__(self, profiles: Mapping[UUID, UserProfile]) -> None:
        self.profiles = profiles
        self.calls = 0

    async def get(self, *, user_id: UUID) -> UserProfile | None:
        self.calls += 1
        return self.profiles.get(user_id)

    async def save(
        self,
        *,
        user_id: UUID,
        profile: UserProfile,
    ) -> UserProfile:
        raise NotImplementedError


class FakeAssistantProfiles:
    def __init__(self, profiles: Mapping[UUID, AssistantProfile]) -> None:
        self.profiles = profiles

    async def get(self, *, user_id: UUID) -> AssistantProfile | None:
        return self.profiles.get(user_id)

    async def save(
        self,
        *,
        user_id: UUID,
        profile: AssistantProfile,
    ) -> AssistantProfile:
        raise NotImplementedError


class FakeConversationStore:
    def __init__(self, user_id: UUID, chat_id: int) -> None:
        self.user_id = user_id
        self.chat_id = chat_id

    async def load(self) -> str:
        return "No conversations yet"

    async def save(self, *, prompt: str, response_text: str, model: str) -> None:
        return None

    async def save_tool_call(
        self,
        *,
        interaction: InternalToolCallInteraction,
        model: str,
    ) -> None:
        return None


def resolved_user(telegram_id: int, name: str) -> ResolvedUser:
    user_id = uuid4()
    plan = Plan(
        code="basic",
        monthly_request_limit=480,
        active=True,
        created_at=NOW,
        updated_at=NOW,
    )
    user = User(
        id=user_id,
        display_name=name,
        plan_code=plan.code,
        subscription_status=SubscriptionStatus.ACTIVE,
        subscription_valid_until=None,
        subscription_synced_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    identity = ExternalIdentity(
        id=uuid4(),
        user_id=user_id,
        provider="telegram",
        external_user_id=str(telegram_id),
        display_name=name,
        created_at=NOW,
        updated_at=NOW,
    )
    return ResolvedUser(user, plan, identity)


def test_runtime_is_immutable_and_isolates_two_users() -> None:
    first = resolved_user(101, "First")
    second = resolved_user(202, "Second")
    user_profiles = {
        item.user.id: UserProfile(
            user_id=item.user.id,
            created_at=NOW,
            updated_at=NOW,
            preferred_name=item.user.display_name,
            locale="en-US",
            timezone="UTC",
            latitude=Decimal("1"),
            longitude=Decimal("2"),
            personal_history=f"{item.user.display_name} history",
        )
        for item in (first, second)
    }
    assistant_profiles = {
        item.user.id: AssistantProfile(
            user_id=item.user.id,
            created_at=NOW,
            updated_at=NOW,
            display_name="Harle",
            profile_text=f"Assistant for {item.user.display_name}",
        )
        for item in (first, second)
    }
    factory = UserRuntimeFactory(
        identity=IdentityService(FakeAccounts({101: first, 202: second})),
        subscriptions=SubscriptionService(clock=lambda: NOW),
        user_profiles=FakeUserProfiles(user_profiles),
        assistant_profiles=FakeAssistantProfiles(assistant_profiles),
        conversation_store_builder=FakeConversationStore,
    )

    first_runtime = asyncio.run(
        factory.create(telegram_user_id=101, telegram_chat_id=1001),
    )
    second_runtime = asyncio.run(
        factory.create(telegram_user_id=202, telegram_chat_id=2002),
    )

    assert first_runtime.user_profile.personal_history == "First history"
    assert second_runtime.user_profile.personal_history == "Second history"
    assert isinstance(first_runtime.conversation_store, FakeConversationStore)
    assert isinstance(second_runtime.conversation_store, FakeConversationStore)
    assert first_runtime.conversation_store.user_id == first.user.id
    assert second_runtime.conversation_store.user_id == second.user.id
    attribute = "telegram_chat_id"
    with pytest.raises(FrozenInstanceError):
        setattr(first_runtime, attribute, 9)


def test_unknown_identity_stops_before_profile_loading() -> None:
    profiles = FakeUserProfiles({})
    factory = UserRuntimeFactory(
        identity=IdentityService(FakeAccounts({})),
        subscriptions=SubscriptionService(clock=lambda: NOW),
        user_profiles=profiles,
        assistant_profiles=FakeAssistantProfiles({}),
        conversation_store_builder=FakeConversationStore,
    )

    with pytest.raises(UnknownIdentityError):
        asyncio.run(factory.create(telegram_user_id=404, telegram_chat_id=1))

    assert profiles.calls == 0
