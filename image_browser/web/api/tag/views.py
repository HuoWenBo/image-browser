from fastapi import APIRouter, Query

from image_browser.db import core
from image_browser.db.dependencies import DBConnection
from image_browser.web.api.tag.schema import TagSearchItem

router = APIRouter()


@router.get("", response_model=list[TagSearchItem])
async def search_tags(
    query: str = Query(min_length=1),
    limit: int = Query(ge=1, le=50, default=10),
    *,
    conn: DBConnection,
) -> list[TagSearchItem]:
    """Search the tag directory for the add-tag suggestion dropdown."""
    items = await core.search_tags(conn, query, limit)
    return [TagSearchItem(**item) for item in items]
