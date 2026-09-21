from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from zoneinfo import ZoneInfo

from harle_domain.accounts import ResolvedUser
from harle_domain.events import EventType, InteractionEvent, InternalEvent
from harle_domain.messaging import OutboundMessenger
from harle_domain.tools import HarleToolStore
from harle_services.access import PreflightService
from harle_services.assistant import generate_response
from harle_services.runtime import UserRuntimeFactory
from harle_utils import (
    InactiveSubscriptionError,
    MissingProfileError,
    UnknownIdentityError,
)

from .interactions import InteractionEventService
from .quota import (
    EventNotificationQuotaService,
    NotificationQuotaExceeded,
    NotificationQuotaReservation,
    NotificationQuotaSkip,
)

ScheduledToolStoreBuilder = Callable[[ResolvedUser, str], HarleToolStore]


class EventNotificationOutcome(str, Enum):
    DELIVERED = "delivered"
    ALREADY_DELIVERED = "already_delivered"
    QUOTA_EXCEEDED = "quota_exceeded"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class EventNotificationService:
    preflight: PreflightService
    users: UserRuntimeFactory
    messenger: OutboundMessenger
    quotas: EventNotificationQuotaService
    interactions: InteractionEventService
    tool_store_builder: ScheduledToolStoreBuilder

    async def notify(self, event: InternalEvent) -> EventNotificationOutcome:
        try:
            resolved_user = await self.preflight.resolve_active_user(event.user_id)
            chat_id = _telegram_chat_id(resolved_user.identity.external_user_id)
            user_runtime = await self.users.create_for_resolved_user(
                resolved_user=resolved_user,
                telegram_chat_id=chat_id,
            )
        except (
            InactiveSubscriptionError,
            MissingProfileError,
            UnknownIdentityError,
            ValueError,
        ):
            return EventNotificationOutcome.SKIPPED

        admission = await self.quotas.reserve(
            event=event,
            monthly_limit=resolved_user.plan.monthly_notification_limit,
            period=resolved_user.user.require_subscription_period(),
        )
        if admission is NotificationQuotaSkip.ALREADY_DELIVERED:
            return EventNotificationOutcome.ALREADY_DELIVERED
        if admission is NotificationQuotaSkip.ALREADY_IN_FLIGHT:
            return EventNotificationOutcome.SKIPPED
        if isinstance(admission, NotificationQuotaExceeded):
            await self._send_quota_exhausted_notice(
                admission,
                chat_id=chat_id,
                locale=user_runtime.user_profile.locale,
            )
            return EventNotificationOutcome.QUOTA_EXCEEDED
        if not isinstance(admission, NotificationQuotaReservation):
            raise RuntimeError("Unexpected notification quota admission.")

        try:
            generated = await generate_response(
                prompt=_notification_prompt(event),
                user_runtime=user_runtime,
                tool_store=self.tool_store_builder(
                    resolved_user,
                    user_runtime.user_profile.timezone,
                ),
            )
            await self.messenger.send_message(
                chat_id=chat_id,
                text=generated.result.response_text,
            )
            await generated.harle.save_scheduled(run_result=generated.result)
            await self.interactions.record_agent_message(user_id=event.user_id)
            await self.quotas.complete(admission)
            return EventNotificationOutcome.DELIVERED
        finally:
            self.quotas.release(admission)

    async def notify_interaction(
        self,
        event: InteractionEvent,
    ) -> EventNotificationOutcome:
        try:
            resolved_user = await self.preflight.resolve_active_user(event.user_id)
            chat_id = _telegram_chat_id(resolved_user.identity.external_user_id)
            user_runtime = await self.users.create_for_resolved_user(
                resolved_user=resolved_user,
                telegram_chat_id=chat_id,
            )
        except (
            InactiveSubscriptionError,
            MissingProfileError,
            UnknownIdentityError,
            ValueError,
        ):
            return EventNotificationOutcome.SKIPPED

        generated = await generate_response(
            prompt=_interaction_prompt(),
            user_runtime=user_runtime,
            tool_store=self.tool_store_builder(
                resolved_user,
                user_runtime.user_profile.timezone,
            ),
        )
        await self.messenger.send_message(
            chat_id=chat_id,
            text=generated.result.response_text,
        )
        await generated.harle.save_scheduled(run_result=generated.result)
        await self.interactions.record_agent_message(user_id=event.user_id)
        return EventNotificationOutcome.DELIVERED

    async def _send_quota_exhausted_notice(
        self,
        exceeded: NotificationQuotaExceeded,
        *,
        chat_id: int,
        locale: str,
    ) -> None:
        if not await self.quotas.claim_exhaustion_notice(exceeded):
            return
        await self.messenger.send_message(
            chat_id=chat_id,
            text=_quota_exhausted_text(exceeded, locale),
        )
        await self.quotas.mark_exhaustion_notice_delivered(exceeded)


def _notification_prompt(event: InternalEvent) -> str:
    timezone_info = ZoneInfo(event.timezone)
    local_start = event.starts_at.astimezone(timezone_info)
    local_end = event.ends_at.astimezone(timezone_info)
    event_context = (
        "the user's real-life agenda"
        if event.event_type is EventType.USER_EVENT
        else "an internal assistant reminder or task owned by the user"
    )
    lead_minutes = int(
        (event.starts_at - event.notification_window_start) / timedelta(minutes=1),
    )
    return (
        "This is an automatic scheduled wake-up, not a new user message. "
        f"Treat this event as {event_context}. "
        "Write only a brief, natural Telegram notification in the user's language. "
        "Use only available read-only tools when useful and do not claim the user "
        "just sent this request. "
        f"Title: {event.title}\n"
        f"Description: {event.description or 'No description'}\n"
        f"Local start: {local_start.isoformat()}\n"
        f"Local end: {local_end.isoformat()}\n"
        f"All day: {event.all_day}\n"
        f"Notification lead minutes: {lead_minutes}"
    )


def _interaction_prompt() -> str:
    return (
        "This is an automatic interaction wake-up, not a new user message. "
        "Based on the user's conversation history and available current context, "
        "choose one natural and useful thing to say or ask. You may use available "
        "read-only tools when useful. Write only a brief Telegram message in the "
        "user's language. Do not mention this wake-up or claim the user just wrote."
    )


def _telegram_chat_id(external_user_id: str) -> int:
    chat_id = int(external_user_id)
    if chat_id <= 0:
        raise ValueError("Telegram identity must be a positive integer.")
    return chat_id


def _quota_exhausted_text(
    exceeded: NotificationQuotaExceeded,
    locale: str,
) -> str:
    resets_at = exceeded.resets_at.isoformat().replace("+00:00", "Z")
    if locale.casefold().startswith("es"):
        return (
            f"Alcanzaste el límite de {exceeded.limit} notificaciones de eventos "
            f"para este período. Tu disponibilidad se restablece el {resets_at}."
        )
    return (
        f"You reached your limit of {exceeded.limit} event notifications "
        "for this subscription period. "
        f"Your allowance resets at {resets_at}."
    )
