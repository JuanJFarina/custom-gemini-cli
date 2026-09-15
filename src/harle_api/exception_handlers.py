from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from harle_utils import AccessDeniedError


async def access_denied_handler(
    request: Request,
    error: Exception,
) -> JSONResponse:
    del request, error
    return JSONResponse(content={"ok": True, "accepted": False})


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AccessDeniedError, access_denied_handler)
