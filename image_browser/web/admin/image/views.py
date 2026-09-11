from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from image_browser.templates import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index(
    *,
    request: Request,
) -> HTMLResponse:
    """Render the gallery home page."""
    return templates.TemplateResponse(
        request,
        "index.html",
    )


@router.get("/image", response_class=HTMLResponse)
async def image_admin(
    *,
    request: Request,
) -> HTMLResponse:
    """Render the image management page."""
    return templates.TemplateResponse(
        request,
        "admin/image.html",
    )
