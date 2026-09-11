from harle_api.settings import ApiSettings
from harle_services.bootstrap import (
    ProcessRuntime,
    close_process_runtime,
    create_process_runtime,
)

ApiRuntime = ProcessRuntime


async def create_runtime(settings: ApiSettings) -> ApiRuntime:
    return await create_process_runtime(
        database_url=settings.POSTGRES_DATABASE_URL,
        pool_min_size=settings.POSTGRES_POOL_MIN_SIZE,
        pool_max_size=settings.POSTGRES_POOL_MAX_SIZE,
    )


async def close_runtime(runtime: ApiRuntime) -> None:
    await close_process_runtime(runtime)
