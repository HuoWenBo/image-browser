import sys

import uvicorn

from image_browser.settings import settings


def main() -> None:
    """Entrypoint of the application."""
    # On Windows, psycopg async requires a Selector event loop; uvicorn
    # builds the loop from its ``loop`` option, so point it at our factory
    # (also inherited by reload / worker subprocesses).
    loop = "image_browser.loop:selector_loop_factory" if sys.platform == "win32" else "auto"
    uvicorn.run(
        "image_browser.web.application:get_app",
        workers=settings.workers_count,
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_level=settings.log_level.value.lower(),
        loop=loop,
        factory=True,
    )


if __name__ == "__main__":
    main()
