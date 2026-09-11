import asyncpg


async def create_postgres_pool(
    *,
    database_url: str,
    min_size: int,
    max_size: int,
) -> asyncpg.Pool:
    pool = await asyncpg.create_pool(
        dsn=database_url,
        min_size=min_size,
        max_size=max_size,
    )
    if pool is None:
        raise RuntimeError("Could not create PostgreSQL connection pool.")
    return pool
