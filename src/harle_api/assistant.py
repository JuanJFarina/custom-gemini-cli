from asyncio import Task

import httpx

from harle_agent.agent import Harle
from harle_agent.models import HarleStores, HarleToolStore
from harle_agent.stores import SQLiteConversationStore
from harle_api.settings import ApiSettings, get_settings
from harle_api.telegram import (
    IncomingTelegramMessage,
    send_message,
    send_typing_action,
)


async def process_telegram_message(
    message: IncomingTelegramMessage,
    settings: ApiSettings | None = None,
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
        response, saving_task = await _generate_response(message, settings)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        response = f"Gemini request failed: {exc}"

    await send_message(
        bot_token=settings.TELEGRAM_BOT_TOKEN,
        chat_id=message.chat_id,
        text=response,
    )
    if saving_task is not None:
        await saving_task


async def _generate_response(
    message: IncomingTelegramMessage,
    settings: ApiSettings | None = None,
) -> tuple[str, Task[None]]:
    settings = settings or get_settings()
    harle_stores = HarleStores(
        conversation_store=SQLiteConversationStore(
            database_path=settings.RESOLVED_SQLITE_PATH,
            chat_id=message.chat_id,
            user_id=message.user_id,
        ),
        tool_store=HarleToolStore(),
    )
    harle = Harle(
        stores=harle_stores,
    )
    return await harle.call(message.text)
