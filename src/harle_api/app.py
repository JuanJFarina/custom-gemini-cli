from typing import Annotated, Any

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

from harle_agent import __version__
from harle_api.assistant import process_telegram_message
from harle_api.settings import get_settings
from harle_api.telegram import extract_text_message

app = FastAPI(
    title="Custom Gemini Telegram Bot",
    description="Telegram webhook for the custom Gemini assistant.",
    version=__version__,
)


@app.get("/healthcheck")
async def get_healthcheck() -> JSONResponse:
    return JSONResponse(content={"status": "OK"})


@app.post("/telegram/webhook")
async def post_telegram_webhook(
    update: dict[str, Any],
    background_tasks: BackgroundTasks,
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

    if message.user_id != settings.TELEGRAM_ALLOWED_USER_ID:
        return JSONResponse(content={"ok": True, "accepted": False})

    background_tasks.add_task(process_telegram_message, message=message)
    return JSONResponse(content={"ok": True, "accepted": True})
