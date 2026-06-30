from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from custom_gemini_bot.settings import BotSettings
from custom_gemini_bot.storage import SQLiteConversationStore
from custom_gemini_bot.telegram import (
    IncomingTelegramMessage,
    send_message,
    send_typing_action,
)
from custom_gemini_cli.config import DEFAULT_MODEL
from custom_gemini_cli.gemini import (
    create_client,
    extract_response_text,
    generate_content,
    is_unavailable_model_error,
)
from custom_gemini_cli.memory import PERSONAL_HISTORY_PATH
from custom_gemini_cli.prompts.system import SYSTEM_PROMPT
from custom_gemini_cli.runtime_context import (
    get_current_time_and_date,
    get_current_weather,
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
    store = SQLiteConversationStore(settings.sqlite_path)

    latest_conversations = store.load_recent_context(
        telegram_chat_id=message.chat_id,
        telegram_user_id=message.user_id,
    )
    system_instruction = SYSTEM_PROMPT.format(
        current_time_and_date=get_current_time_and_date(),
        current_weather=get_current_weather(),
        juan_personal_history_summary=_load_personal_history(PERSONAL_HISTORY_PATH),
        latest_conversations=latest_conversations,
    )

    model = settings.gemini_model
    effective_model = model
    client = create_client(api_key=api_key)

    try:
        response = generate_content(
            client=client,
            model=model,
            prompt=message.text,
            system_instruction=system_instruction,
        )
    except Exception as exc:
        if model != DEFAULT_MODEL and is_unavailable_model_error(exc):
            response = generate_content(
                client=client,
                model=DEFAULT_MODEL,
                prompt=message.text,
                system_instruction=system_instruction,
            )
            effective_model = DEFAULT_MODEL
        else:
            raise
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()

    response_text = extract_response_text(response)
    store.save_conversation(
        telegram_chat_id=message.chat_id,
        telegram_user_id=message.user_id,
        prompt=message.text,
        response=response_text,
        model=effective_model,
    )
    return response_text


def _load_personal_history(path: Path) -> str:
    if not path.is_file():
        return "No personal history has been recorded yet."

    content = path.read_text(encoding="utf-8").strip()
    return content or "No personal history has been recorded yet."

