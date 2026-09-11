from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from image_browser.templates import templates

router = APIRouter()


@router.get("/tag", response_class=HTMLResponse)
async def image_tag_admin(
    *,
    request: Request,
) -> HTMLResponse:
    """Render the image tag management page."""
    return templates.TemplateResponse(
        request,
        "admin/tag.html",
    )
