from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from harle_agent import __version__
from harle_api.assistant import process_telegram_messages
from harle_api.exception_handlers import register_exception_handlers
from harle_api.runtime import ApiRuntime, close_runtime, create_runtime
from harle_api.settings import get_settings
from harle_api.telegram import extract_text_message
from harle_services.messaging import MessageSubmissionStatus


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    runtime = await create_runtime(get_settings())
    app.state.runtime = runtime
    runtime.scheduler.start()
    try:
        yield
    finally:
        await close_runtime(runtime)


harle_app = FastAPI(
    title="Custom Gemini Telegram Bot",
    description="Telegram webhook for the custom Gemini assistant.",
    version=__version__,
    lifespan=lifespan,
)
register_exception_handlers(harle_app)


@harle_app.get("/healthcheck")
async def get_healthcheck() -> JSONResponse:
    return JSONResponse(content={"status": "OK"})


@harle_app.post("/telegram/webhook")
async def post_telegram_webhook(
    update: Mapping[str, object],
    background_tasks: BackgroundTasks,
    request: Request,
    x_telegram_bot_api_secret_token: Annotated[
        str | None,
        Header(alias="X-Telegram-Bot-Api-Secret-Token"),
    ] = None,
) -> JSONResponse:
    settings = get_settings()
    if x_telegram_bot_api_secret_token != settings.TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid Telegram webhook secret.")

    message = extract_text_message(update)
    if message is None:
        return JSONResponse(content={"ok": True, "accepted": False})

    runtime = _runtime(request)
    submission = await runtime.messages.receive(
        update_id=message.update_id,
        telegram_user_id=message.user_id,
        telegram_chat_id=message.chat_id,
        text=message.text,
    )
    if submission.status is MessageSubmissionStatus.RATE_LIMITED:
        temporary_ban = submission.temporary_ban
        if temporary_ban is None:
            raise RuntimeError("Rate-limited submission has no ban details.")
        retry_at = _utc_boundary(temporary_ban.blocked_until)
        if temporary_ban.notify_user:
            background_tasks.add_task(
                runtime.messenger.send_message,
                chat_id=message.chat_id,
                text=f"You're sending messages too quickly. Try again after {retry_at}.",
            )
        return JSONResponse(
            content={
                "ok": True,
                "accepted": False,
                "reason": "temporarily_banned",
                "retry_at": retry_at,
                "notified": temporary_ban.notify_user,
            },
        )
    if submission.status in {
        MessageSubmissionStatus.DUPLICATE,
        MessageSubmissionStatus.DELIVERED,
    }:
        return JSONResponse(
            content={"ok": True, "accepted": False, "duplicate": True},
        )

    if submission.status is MessageSubmissionStatus.INTERRUPTED:
        return JSONResponse(
            content={
                "ok": True,
                "accepted": False,
                "reason": "interrupted_after_tool_execution",
            },
        )

    if submission.starts_processing:
        background_tasks.add_task(
            process_telegram_messages,
            telegram_user_id=message.user_id,
            runtime=runtime,
        )

    return JSONResponse(
        content={
            "ok": True,
            "accepted": True,
            "disposition": submission.status.value,
        },
    )


def _runtime(request: Request) -> ApiRuntime:
    runtime = getattr(request.app.state, "runtime", None)
    if not isinstance(runtime, ApiRuntime):
        raise RuntimeError("API runtime is not initialized.")
    return runtime


def _utc_boundary(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
