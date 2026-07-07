from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from harle_agent import __version__
from harle_api.assistant import process_telegram_message
from harle_api.runtime import ApiRuntime, close_runtime, create_runtime
from harle_api.settings import get_settings
from harle_api.telegram import extract_text_message


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


@harle_app.get("/healthcheck")
async def get_healthcheck() -> JSONResponse:
    return JSONResponse(content={"status": "OK"})


@harle_app.post("/telegram/webhook")
async def post_telegram_webhook(
    update: dict[str, Any],
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

    if message.user_id != settings.TELEGRAM_ALLOWED_USER_ID:
        return JSONResponse(content={"ok": True, "accepted": False})

    background_tasks.add_task(
        process_telegram_message,
        message=message,
        runtime=_runtime(request),
    )
    return JSONResponse(content={"ok": True, "accepted": True})


def _runtime(request: Request) -> ApiRuntime:
    runtime = getattr(request.app.state, "runtime", None)
    if not isinstance(runtime, ApiRuntime):
        raise RuntimeError("API runtime is not initialized.")
    return runtime
