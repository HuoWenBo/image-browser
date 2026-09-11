import os
from os import PathLike
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

from image_browser.log import configure_logging
from image_browser.web import admin, api
from image_browser.web.lifespan import lifespan_setup

APP_ROOT = Path(__file__).parent.parent.parent


class NoCacheStaticFiles(StaticFiles):
    """Static files served without browser caching (development friendly)."""

    def file_response(
        self,
        full_path: str | PathLike[str],
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        """Build the response and disable browser caching."""
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers["Cache-Control"] = "no-cache"
        return response


def get_app() -> FastAPI:
    """
    Get FastAPI application.

    This is the main constructor of an application.

    :return: application.
    """
    configure_logging()
    app = FastAPI(
        title="图片浏览器",
        lifespan=lifespan_setup,
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    # Main router for the API.
    app.include_router(router=api.router, prefix="/api")
    app.include_router(router=admin.router, prefix="/admin")
    # Adds static directory.
    # This directory is used to access swagger files.
    app.mount(
        "/static",
        NoCacheStaticFiles(directory=APP_ROOT / "static"),
        name="static",
    )
    app.mount("/image", StaticFiles(directory=APP_ROOT / "images"), name="image")

    return app
