from collections.abc import Mapping
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from harle_api.assistant import process_telegram_messages
from harle_api.dependencies import get_account_runtime, get_runtime
from harle_api.settings import get_settings
from harle_api.telegram import (
    IncomingTelegramMessage,
    UnsupportedTelegramMedia,
    extract_telegram_link_token,
    extract_telegram_message,
)
from harle_services.accounts import TelegramLinkCommand
from harle_services.bootstrap import ProcessRuntime
from harle_services.messaging import (
    MessageFragment,
    MessageSubmission,
    MessageSubmissionStatus,
)

router = APIRouter()


@router.post("/telegram/webhook")
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
    runtime = get_runtime(request)
    if isinstance(message, UnsupportedTelegramMedia):
        return await _reject_unsupported_media(
            message=message,
            background_tasks=background_tasks,
            runtime=runtime,
        )
    link_token = extract_telegram_link_token(message.text)
    if link_token is not None:
        result = await get_account_runtime(
            request,
        ).telegram_link_commands.handle(
            command=TelegramLinkCommand(
                update_id=message.update_id,
                telegram_user_id=message.user_id,
                telegram_chat_id=message.chat_id,
                telegram_display_name=message.user_name,
                token=link_token,
            ),
        )
        return JSONResponse(
            content={
                "ok": True,
                "accepted": result.disposition.value == "account_link",
                "disposition": result.disposition.value,
                **(
                    {
                        "retry_at": _utc_boundary(result.retry_at),
                        "notified": result.notified,
                    }
                    if result.retry_at is not None
                    else {}
                ),
            },
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
    runtime: ProcessRuntime,
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
    runtime: ProcessRuntime,
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


def _utc_boundary(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _rate_limited_response(
    *,
    submission: MessageSubmission,
    chat_id: int,
    background_tasks: BackgroundTasks,
    runtime: ProcessRuntime,
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
