from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from harle_agent import __version__
from harle_api.assistant import process_telegram_message
from harle_api.exception_handlers import register_exception_handlers
from harle_api.runtime import ApiRuntime, close_runtime, create_runtime
from harle_api.settings import get_settings
from harle_api.telegram import extract_text_message, send_message
from harle_services.access import QuotaExceeded, TemporaryBan
from harle_services.runtime import RequestAccepted


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    runtime = await create_runtime(get_settings())
    app.state.runtime = runtime
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
    claimed = await runtime.telegram_updates.claim(
        update_id=message.update_id,
        telegram_user_id=message.user_id,
        telegram_chat_id=message.chat_id,
    )
    if not claimed:
        return JSONResponse(
            content={"ok": True, "accepted": False, "duplicate": True},
        )

    admission = await runtime.admissions.admit(
        telegram_user_id=message.user_id,
        telegram_chat_id=message.chat_id,
        telegram_update_id=message.update_id,
    )
    if isinstance(admission, TemporaryBan):
        retry_at = _utc_boundary(admission.blocked_until)
        if admission.notify_user:
            background_tasks.add_task(
                send_message,
                bot_token=settings.TELEGRAM_BOT_TOKEN,
                chat_id=message.chat_id,
                text=f"You're sending messages too quickly. Try again after {retry_at}.",
            )
        return JSONResponse(
            content={
                "ok": True,
                "accepted": False,
                "reason": "temporarily_banned",
                "retry_at": retry_at,
                "notified": admission.notify_user,
            },
        )

    if isinstance(admission, QuotaExceeded):
        reset_at = _utc_boundary(admission.resets_at)
        background_tasks.add_task(
            send_message,
            bot_token=settings.TELEGRAM_BOT_TOKEN,
            chat_id=message.chat_id,
            text=(
                f"You have {admission.remaining} requests remaining this month. "
                f"Your allowance resets at {reset_at}."
            ),
        )
        return JSONResponse(
            content={
                "ok": True,
                "accepted": False,
                "reason": "monthly_quota_exceeded",
                "remaining": admission.remaining,
                "reset_at": reset_at,
            },
        )

    if not isinstance(admission, RequestAccepted):
        raise RuntimeError("Unexpected request admission result.")
    background_tasks.add_task(
        process_telegram_message,
        message=message,
        user_runtime=admission.user_runtime,
        user_work=runtime.user_work,
        usage_quota=runtime.usage_quota,
        quota_reservation=admission.quota_reservation,
    )
    return JSONResponse(
        content={
            "ok": True,
            "accepted": True,
            "remaining": admission.quota_reservation.remaining,
            "reset_at": _utc_boundary(admission.quota_reservation.resets_at),
        },
    )


def _runtime(request: Request) -> ApiRuntime:
    runtime = getattr(request.app.state, "runtime", None)
    if not isinstance(runtime, ApiRuntime):
        raise RuntimeError("API runtime is not initialized.")
    return runtime


def _utc_boundary(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
