from dataclasses import dataclass
from datetime import timedelta
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


@dataclass(frozen=True, slots=True)
class EventNotificationService:
    preflight: PreflightService
    users: UserRuntimeFactory
    messenger: OutboundMessenger

    async def notify(self, event: InternalEvent) -> bool:
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
            return False

        generated = await generate_response(
            prompt=_notification_prompt(event),
            user_runtime=user_runtime,
            tool_store=HarleToolStore(),
        )
        await self.messenger.send_message(
            chat_id=chat_id,
            text=generated.result.response_text,
        )
        return True


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
