import threading
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import psycopg_pool
from fastapi import FastAPI
from imgutils import tagging
from loguru import logger
from PIL import Image as PILImage

from image_browser.settings import settings


async def _setup_db(app: FastAPI) -> None:
    """
    Creates connection pool for timescaledb.

    :param app: current FastAPI app.
    """
    app.state.db_pool = psycopg_pool.AsyncConnectionPool(
        conninfo=str(settings.db_url),
        open=False,
        kwargs={
            "options": f"-c search_path={settings.db_schema}",
        },
    )
    await app.state.db_pool.open(wait=True)


def _warmup_image() -> PILImage.Image:
    """Pick a real album image to warm up the model.

    Falls back to a tiny generated one when the album is empty.

    :return: a PIL image usable for model inference.
    """
    suffixes = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    for path in sorted(settings.images_dir_path.rglob("*")):
        if path.is_file() and path.suffix.lower() in suffixes:
            try:
                with PILImage.open(path) as img:
                    return img.convert("RGB")
            except Exception:
                logger.debug("Skipped warmup image {}", path)
                continue
    logger.warning("No album image found for model warmup; using a generated one")
    return PILImage.new("RGB", (64, 64), (128, 128, 128))


def _preload_tagging_model() -> None:
    """Warm up the local tagging model in a background thread.

    The first get_pixai_tags call loads the model files, which can take a
    long time; preloading here keeps the first real request responsive.
    """
    try:
        image = _warmup_image()
        logger.info(f"Preloading tagging model from 'models--deepghs--pixai-tagger-{settings.tag_model_name}'")
        st = time.time()
        tagging.get_pixai_tags(image, settings.tag_model_name, None)
        elapsed = time.time() - st
        logger.info(f"Tagging model preloaded: {settings.tag_model_name}, took {elapsed:.1f} seconds")
    except Exception as exc:
        logger.exception("Tagging model preload failed")
        raise exc


@asynccontextmanager
async def lifespan_setup(
    app: FastAPI,
) -> AsyncGenerator[None]:  # pragma: no cover
    """
    Actions to run on application startup.

    This function uses fastAPI app to store data
    in the state, such as db_engine.

    :param app: the fastAPI application.
    :return: function that actually performs actions.
    """

    app.middleware_stack = None
    await _setup_db(app)
    app.middleware_stack = app.build_middleware_stack()

    # Preload the tagging model off the event loop so the first real request
    # does not pay the model loading cost.
    threading.Thread(
        target=_preload_tagging_model,
        name="tagging-model-preload",
        daemon=True,
    ).start()

    yield
    await app.state.db_pool.close()
