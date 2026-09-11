from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from image_browser.templates import templates

router = APIRouter()


@router.get("/translation", response_class=HTMLResponse)
async def translation_page(request: Request) -> HTMLResponse:
    """Render the tag translation admin page."""
    return templates.TemplateResponse(request, "admin/translation.html")
