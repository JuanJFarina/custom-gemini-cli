from asyncio import Task

import httpx

from harle_agent.agent import Harle
from harle_agent.models import ConversationStore, HarleStores, HarleToolStore
from harle_agent.retry_decorator import ASSISTANT_FAILURES
from harle_agent.stores import (
    PostgresConversationStore,
    SQLiteConversationStore,
)
from harle_api.runtime import ApiRuntime
from harle_api.settings import ApiSettings, get_settings
from harle_api.telegram import (
    IncomingTelegramMessage,
    send_message,
    send_typing_action,
)


async def process_telegram_message(
    message: IncomingTelegramMessage,
    settings: ApiSettings | None = None,
    runtime: ApiRuntime | None = None,
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
            settings,
            runtime=runtime,
        )
    except ASSISTANT_FAILURES as exc:
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
    runtime: ApiRuntime | None = None,
) -> tuple[str, Task[None]]:
    settings = settings or get_settings()
    harle_stores = HarleStores(
        conversation_store=_conversation_store(
            message=message,
            settings=settings,
            runtime=runtime,
        ),
        tool_store=HarleToolStore(),
    )
    harle = Harle(
        stores=harle_stores,
    )
    return await harle.call(message.text)


def _conversation_store(
    *,
    message: IncomingTelegramMessage,
    settings: ApiSettings,
    runtime: ApiRuntime | None,
) -> ConversationStore:
    if settings.POSTGRES_DATABASE_URL:
        if runtime is None or runtime.postgres is None:
            raise RuntimeError("Postgres runtime is not initialized.")

        return PostgresConversationStore(
            pool=runtime.postgres.pool,
            user_id=runtime.postgres.owner_user_id,
            user_name=runtime.postgres.owner_user_name,
            telegram_chat_id=message.chat_id,
        )

    return SQLiteConversationStore(
        database_path=settings.RESOLVED_SQLITE_PATH,
        chat_id=message.chat_id,
        user_id=message.user_id,
    )
