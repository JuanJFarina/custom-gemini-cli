from asyncio import sleep

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/healthcheck")
async def get_healthcheck() -> JSONResponse:
    await sleep(20)
    return JSONResponse(content={"status": "OK"})
