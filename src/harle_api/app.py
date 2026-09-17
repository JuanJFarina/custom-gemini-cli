from asyncio import sleep
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
from harle_api.telegram import (
    IncomingTelegramMessage,
    UnsupportedTelegramMedia,
    extract_telegram_message,
)
from harle_services.messaging import (
    MessageFragment,
    MessageSubmission,
    MessageSubmissionStatus,
)


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
    await sleep(20)
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

    message = extract_telegram_message(
        update,
        maximum_request_size=settings.MAX_MEDIA_REQUEST_SIZE,
    )
    if message is None:
        return JSONResponse(content={"ok": True, "accepted": False})

    runtime = _runtime(request)
    if isinstance(message, UnsupportedTelegramMedia):
        return await _reject_unsupported_media(
            message=message,
            background_tasks=background_tasks,
            runtime=runtime,
        )
    return await _submit_message(
        message=message,
        background_tasks=background_tasks,
        runtime=runtime,
    )


async def _reject_unsupported_media(
    *,
    message: UnsupportedTelegramMedia,
    background_tasks: BackgroundTasks,
    runtime: ApiRuntime,
) -> JSONResponse:
    submission = await runtime.messages.reject(
        update_id=message.update_id,
        telegram_user_id=message.user_id,
        telegram_chat_id=message.chat_id,
        text=f"[Rejected Telegram media: {message.reason}]",
    )
    rate_limited = _rate_limited_response(
        submission=submission,
        chat_id=message.chat_id,
        background_tasks=background_tasks,
        runtime=runtime,
    )
    if rate_limited is not None:
        return rate_limited
    if submission.status is MessageSubmissionStatus.DUPLICATE:
        return JSONResponse(
            content={"ok": True, "accepted": False, "duplicate": True},
        )
    if submission.status is not MessageSubmissionStatus.REJECTED:
        raise RuntimeError("Unexpected rejected-media disposition.")
    background_tasks.add_task(
        runtime.messenger.send_message,
        chat_id=message.chat_id,
        text=_media_rejection_message(message.reason),
    )
    return JSONResponse(
        content={
            "ok": True,
            "accepted": False,
            "reason": message.reason,
        },
    )


async def _submit_message(
    *,
    message: IncomingTelegramMessage,
    background_tasks: BackgroundTasks,
    runtime: ApiRuntime,
) -> JSONResponse:
    submission = await runtime.messages.receive(
        MessageFragment(
            update_id=message.update_id,
            telegram_user_id=message.user_id,
            telegram_chat_id=message.chat_id,
            text=message.text,
            media=message.media,
        ),
    )
    rate_limited = _rate_limited_response(
        submission=submission,
        chat_id=message.chat_id,
        background_tasks=background_tasks,
        runtime=runtime,
    )
    if rate_limited is not None:
        return rate_limited
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


def _rate_limited_response(
    *,
    submission: MessageSubmission,
    chat_id: int,
    background_tasks: BackgroundTasks,
    runtime: ApiRuntime,
) -> JSONResponse | None:
    if submission.status is not MessageSubmissionStatus.RATE_LIMITED:
        return None
    temporary_ban = submission.temporary_ban
    if temporary_ban is None:
        raise RuntimeError("Rate-limited submission has no ban details.")
    retry_at = _utc_boundary(temporary_ban.blocked_until)
    if temporary_ban.notify_user:
        background_tasks.add_task(
            runtime.messenger.send_message,
            chat_id=chat_id,
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


def _media_rejection_message(reason: str) -> str:
    if reason == "media_too_large":
        return "El archivo adjunto es demasiado grande."
    if reason == "unsupported_media_type":
        return "Formato no soportado."
    return "El archivo adjunto no es válido."
