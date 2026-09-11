from collections.abc import AsyncGenerator
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from image_browser.db.dependencies import get_db_pool
from image_browser.settings import settings
from image_browser.web.application import get_app


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """
    Backend for anyio pytest plugin.

    :return: backend name.
    """
    return "asyncio"


async def drop_db() -> None:
    """Drops database after tests."""
    pool = AsyncConnectionPool(conninfo=str(settings.db_url.with_path("/postgres")), open=False)
    await pool.open(wait=True)
    async with pool.connection() as conn:
        await conn.set_autocommit(True)
        await conn.execute(
            "SELECT pg_terminate_backend(pg_stat_activity.pid) "
            "FROM pg_stat_activity "
            "WHERE pg_stat_activity.datname = %(dbname)s "
            "AND pid <> pg_backend_pid();",
            params={
                "dbname": settings.db_base,
            },
        )
        await conn.execute(
            f"DROP DATABASE {settings.db_base}",
        )
    await pool.close()


async def create_db() -> None:
    """Creates database for tests."""
    pool = AsyncConnectionPool(conninfo=str(settings.db_url.with_path("/postgres")), open=False)
    await pool.open(wait=True)
    async with pool.connection() as conn_check:
        res = await conn_check.execute(
            "SELECT 1 FROM pg_database WHERE datname=%(dbname)s",
            params={
                "dbname": settings.db_base,
            },
        )
        db_exists = False
        row = await res.fetchone()
        if row is not None:
            db_exists = row[0]

    if db_exists:
        await drop_db()

    async with pool.connection() as conn_create:
        await conn_create.set_autocommit(True)
        await conn_create.execute(
            f"CREATE DATABASE {settings.db_base};",
        )
    await pool.close()


async def create_tables(connection: AsyncConnection[Any]) -> None:
    """
    Create tables for your database.

    Since psycopg doesn't have migration tool,
    you must create your tables for tests.

    :param connection: connection to database.
    """


@pytest.fixture
async def dbpool() -> AsyncGenerator[AsyncConnectionPool[Any]]:
    """
    Creates database connections pool to test database.

    This connection must be used in tests and for application.

    :yield: database connections pool.
    """
    await create_db()
    pool = AsyncConnectionPool(conninfo=str(settings.db_url), open=False)
    await pool.open(wait=True)

    async with pool.connection() as create_conn:
        await create_tables(create_conn)

    try:
        yield pool
    finally:
        await pool.close()
        await drop_db()


@pytest.fixture
def fastapi_app(
    dbpool: AsyncConnectionPool[Any],
) -> FastAPI:
    """
    Fixture for creating FastAPI app.

    :return: fastapi app with mocked dependencies.
    """
    application = get_app()
    application.dependency_overrides[get_db_pool] = lambda: dbpool
    return application


@pytest.fixture
async def client(fastapi_app: FastAPI, anyio_backend: Any) -> AsyncGenerator[AsyncClient]:
    """
    Fixture that creates client for requesting server.

    :param fastapi_app: the application.
    :yield: client for the app.
    """
    async with AsyncClient(transport=ASGITransport(fastapi_app), base_url="http://test", timeout=2.0) as ac:
        yield ac
