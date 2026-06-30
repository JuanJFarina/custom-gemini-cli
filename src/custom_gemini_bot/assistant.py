from __future__ import annotations

import asyncio

import httpx

from custom_gemini_bot.settings import BotSettings
from custom_gemini_bot.telegram import (
    IncomingTelegramMessage,
    send_message,
    send_typing_action,
)
from custom_gemini_cli.harle import Harle
from custom_gemini_cli.stores.sqlite_store import SQLiteConversationStore
from custom_gemini_cli.tools.expenses import build_expense_tool_from_env


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

    try:
        response_text = await asyncio.to_thread(
            _generate_response,
            settings,
            message,
        )
    except Exception as exc:
        response_text = f"Gemini request failed: {exc}"

    await send_message(
        bot_token=bot_token,
        chat_id=message.chat_id,
        text=response_text,
    )


def _generate_response(
    settings: BotSettings,
    message: IncomingTelegramMessage,
) -> str:
    api_key = settings.require_gemini_api_key()
    harle = Harle(
        model=settings.gemini_model,
        api_key=api_key,
        conversation_store=SQLiteConversationStore(
            database_path=settings.sqlite_path,
            chat_id=message.chat_id,
            user_id=message.user_id,
        ),
        expense_tool=build_expense_tool_from_env(),
    )
    return harle.respond(message.text)

