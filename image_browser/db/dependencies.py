from collections.abc import AsyncGenerator
from typing import Annotated, Any

from fastapi import Depends
from pgvector.psycopg import register_vector_async
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool
from starlette.requests import Request


async def get_db_pool(request: Request) -> AsyncConnectionPool[Any]:
    """
    Return database connections pool.

    :param request: current request.
    :returns: database connections pool.
    """
    return request.app.state.db_pool


DBPool = Annotated[AsyncConnectionPool[Any], Depends(get_db_pool)]


async def get_db_connection(pool: DBPool) -> AsyncGenerator[Any, Any]:
    """Return database connections pool."""
    async with pool.connection() as conn:
        await register_vector_async(conn)
        yield conn


DBConnection = Annotated[AsyncConnection[Any], Depends(get_db_connection)]
