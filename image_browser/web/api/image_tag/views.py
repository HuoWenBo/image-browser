from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response

from image_browser.db import core
from image_browser.db.dependencies import DBConnection
from image_browser.web.api.image_tag.schema import (
    ImageTagAssocCreate,
    ImageTagAssocItem,
    ImageTagAssocListResponse,
)
from image_browser.web.api.pagination import Paginator, calc_total_pages

router = APIRouter()


@router.get("", response_model=ImageTagAssocListResponse)
async def index(
    paginator: Paginator,
    query: str = "",
    *,
    conn: DBConnection,
) -> ImageTagAssocListResponse:
    """List image-tag associations, optionally filtered by filename or tag name."""
    items, total = await core.list_image_tag_assoc(
        conn,
        query,
        paginator.offset,
        paginator.limit,
    )
    return ImageTagAssocListResponse(
        items=[ImageTagAssocItem.model_validate(item) for item in items],
        total=total,
        page=paginator.page,
        per_page=paginator.per_page,
        total_pages=calc_total_pages(total, paginator.per_page),
    )


@router.post("", response_model=ImageTagAssocItem, status_code=status.HTTP_201_CREATED)
async def create(
    payload: ImageTagAssocCreate,
    *,
    conn: DBConnection,
) -> ImageTagAssocItem:
    """Add an existing tag to an image."""
    outcome, tag_id = await core.add_image_tag_assoc(
        conn,
        payload.image_id,
        payload.tag_id,
        payload.score,
    )
    if outcome == "image_missing":
        raise HTTPException(status_code=404, detail="图片不存在")
    if outcome == "tag_missing":
        raise HTTPException(status_code=404, detail="标签不存在, 请从推荐列表中选择")
    if outcome == "duplicate":
        raise HTTPException(status_code=409, detail="该图片已存在此标签")
    tag = await core.get_tag_by_id(conn, tag_id)
    if tag is None:
        raise HTTPException(status_code=500, detail="标签数据异常")
    await conn.commit()
    return ImageTagAssocItem(
        image_id=payload.image_id,
        image_filename="",
        tag_id=tag_id,
        tag_name=tag["name"],
        tag_type=tag["type"],
        score=payload.score,
    )


@router.delete("/{image_id}/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(
    image_id: int,
    tag_id: int,
    *,
    conn: DBConnection,
) -> Response:
    """Delete an image-tag association row."""
    deleted = await core.delete_image_tag_assoc(conn, image_id, tag_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="标签关联不存在")
    await conn.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
