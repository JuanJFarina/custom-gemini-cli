from __future__ import annotations

from asyncio import Task

import httpx

from harle_agent.agent import Harle
from harle_agent.models.harle_models import HarleConfig, HarleStores, HarleToolStore
from harle_agent.stores.sqlite_store import SQLiteConversationStore
from harle_api.settings import BotSettings
from harle_api.telegram import (
    IncomingTelegramMessage,
    send_message,
    send_typing_action,
)


async def process_telegram_message(
    *,
    settings: BotSettings,
    message: IncomingTelegramMessage,
) -> None:
    bot_token = settings.require_telegram_bot_token()

    try:
        await send_typing_action(bot_token=bot_token, chat_id=message.chat_id)
    except httpx.HTTPError:
        pass

    saving_task: Task[None] | None = None

    try:
        response, saving_task = await _generate_response(settings, message)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        response = f"Gemini request failed: {exc}"

    await send_message(
        bot_token=bot_token,
        chat_id=message.chat_id,
        text=response,
    )
    if saving_task is not None:
        await saving_task


async def _generate_response(
    settings: BotSettings,
    message: IncomingTelegramMessage,
) -> tuple[str, Task[None]]:
    api_key = settings.require_gemini_api_key()
    harle_config = HarleConfig(
        model=settings.gemini_model,
        api_key=api_key,
    )
    harle_stores = HarleStores(
        conversation_store=SQLiteConversationStore(
            database_path=settings.sqlite_path,
            chat_id=message.chat_id,
            user_id=message.user_id,
        ),
        tool_store=HarleToolStore(),
    )
    harle = Harle(
        config=harle_config,
        stores=harle_stores,
    )
    return await harle.call(message.text)
