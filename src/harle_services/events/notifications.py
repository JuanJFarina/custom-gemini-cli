from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from zoneinfo import ZoneInfo

from harle_domain.events import EventType, InternalEvent
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

from .quota import (
    EventNotificationQuotaService,
    NotificationQuotaExceeded,
    NotificationQuotaReservation,
    NotificationQuotaSkip,
)


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
                tool_store=HarleToolStore(),
            )
            await self.messenger.send_message(
                chat_id=chat_id,
                text=generated.result.response_text,
            )
            await self.quotas.complete(admission)
            return EventNotificationOutcome.DELIVERED
        finally:
            self.quotas.release(admission)

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
        "Do not call tools or claim the user just sent this request. "
        f"Title: {event.title}\n"
        f"Description: {event.description or 'No description'}\n"
        f"Local start: {local_start.isoformat()}\n"
        f"Local end: {local_end.isoformat()}\n"
        f"All day: {event.all_day}\n"
        f"Notification lead minutes: {lead_minutes}"
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
            f"Alcanzaste el límite mensual de {exceeded.limit} notificaciones "
            f"de eventos. Tu disponibilidad se restablece el {resets_at}."
        )
    return (
        f"You reached your monthly limit of {exceeded.limit} event notifications. "
        f"Your allowance resets at {resets_at}."
    )
