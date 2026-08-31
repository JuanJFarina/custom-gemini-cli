from asyncio import Task

import httpx

from harle_agent.agent import Harle
from harle_agent.models import HarlePersonalContext, HarleStores
from harle_agent.retry_decorator import ASSISTANT_FAILURES
from harle_api.settings import ApiSettings, get_settings
from harle_api.telegram import (
    IncomingTelegramMessage,
    send_message,
    send_typing_action,
)
from harle_services.access import QuotaReservation, UsageQuotaService
from harle_services.messaging import UserWorkCoordinator
from harle_services.runtime import UserRuntime


async def process_telegram_message(
    message: IncomingTelegramMessage,
    user_runtime: UserRuntime,
    user_work: UserWorkCoordinator,
    usage_quota: UsageQuotaService,
    quota_reservation: QuotaReservation,
) -> None:
    try:
        async with user_work.serialize(user_runtime.resolved_user.user.id):
            await _process_telegram_message(
                message=message,
                user_runtime=user_runtime,
                settings=None,
            )
    finally:
        await usage_quota.release(quota_reservation)


async def _process_telegram_message(
    *,
    message: IncomingTelegramMessage,
    user_runtime: UserRuntime,
    settings: ApiSettings | None,
) -> None:
    settings = settings or get_settings()

    try:
        await send_typing_action(
            bot_token=settings.TELEGRAM_BOT_TOKEN,
            chat_id=message.chat_id,
        )
    except httpx.HTTPError:
        pass

    saving_task: Task[None] | None = None

    try:
        response, saving_task = await _generate_response(
            message,
            user_runtime,
        )
    except ASSISTANT_FAILURES:
        response = "I can't respond right now. Please try again shortly."

    try:
        await send_message(
            bot_token=settings.TELEGRAM_BOT_TOKEN,
            chat_id=message.chat_id,
            text=response,
        )
    finally:
        if saving_task is not None:
            await saving_task


async def _generate_response(
    message: IncomingTelegramMessage,
    user_runtime: UserRuntime,
) -> tuple[str, Task[None]]:
    harle_stores = HarleStores(
        conversation_store=user_runtime.conversation_store,
        tool_store=user_runtime.tool_store,
    )
    user_profile = user_runtime.user_profile
    assistant_profile = user_runtime.assistant_profile
    harle = Harle(
        stores=harle_stores,
        personal_context=HarlePersonalContext(
            user_name=user_runtime.resolved_user.user.display_name,
            preferred_name=user_profile.preferred_name,
            locale=user_profile.locale,
            timezone=user_profile.timezone,
            assistant_profile=(
                f"{assistant_profile.display_name}: {assistant_profile.profile_text}"
            ),
            personal_history=(
                user_profile.personal_history
                or "No personal history has been supplied."
            ),
            latitude=(
                float(user_profile.latitude)
                if user_profile.latitude is not None
                else None
            ),
            longitude=(
                float(user_profile.longitude)
                if user_profile.longitude is not None
                else None
            ),
        ),
    )
    return await harle.call(message.text)
