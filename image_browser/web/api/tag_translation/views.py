from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response

from image_browser.db import core
from image_browser.db.dependencies import DBConnection
from image_browser.db.models.image import TagSubType, TagType
from image_browser.web.api.pagination import Paginator, calc_total_pages
from image_browser.web.api.tag_translation.schema import (
    BatchImportRequest,
    BatchImportResult,
    MissingTranslationItem,
    MissingTranslationListResponse,
    TagTranslationCreate,
    TagTranslationItem,
    TagTranslationListResponse,
    TagTranslationUpdate,
)

router = APIRouter()


@router.get("", response_model=TagTranslationListResponse)
async def index(
    paginator: Paginator,
    query: str = "",
    tag_type: TagType | None = Query(default=None),
    sub_type: TagSubType | None = Query(default=None),
    language: str | None = Query(default=None, max_length=16),
    *,
    conn: DBConnection,
) -> TagTranslationListResponse:
    """List tag translations with keyword/type/sub-type/language filtering."""
    items, total = await core.list_tag_translations(
        conn,
        query=query,
        offset=paginator.offset,
        limit=paginator.limit,
        tag_type=tag_type.value if tag_type else None,
        sub_type=sub_type.value if sub_type else None,
        language=language,
    )
    return TagTranslationListResponse(
        items=[TagTranslationItem(**item) for item in items],
        total=total,
        page=paginator.page,
        per_page=paginator.per_page,
        total_pages=calc_total_pages(total, paginator.per_page),
    )


@router.get("/missing", response_model=MissingTranslationListResponse)
async def missing(
    paginator: Paginator,
    query: str = "",
    tag_type: TagType | None = Query(default=None),
    sub_type: TagSubType | None = Query(default=None),
    *,
    conn: DBConnection,
) -> MissingTranslationListResponse:
    """List tag directory entries that have no translation."""
    items, total = await core.list_missing_tag_translations(
        conn,
        query=query,
        offset=paginator.offset,
        limit=paginator.limit,
        tag_type=tag_type.value if tag_type else None,
        sub_type=sub_type.value if sub_type else None,
    )
    return MissingTranslationListResponse(
        items=[MissingTranslationItem(**item) for item in items],
        total=total,
        page=paginator.page,
        per_page=paginator.per_page,
        total_pages=calc_total_pages(total, paginator.per_page),
    )


@router.post("", response_model=TagTranslationItem, status_code=status.HTTP_201_CREATED)
async def create(
    payload: TagTranslationCreate,
    *,
    conn: DBConnection,
) -> TagTranslationItem:
    """Create or update a single tag translation."""
    tag = await core.get_tag_by_id(conn, payload.tag_id)
    if tag is None:
        raise HTTPException(status_code=404, detail="标签不存在")
    await core.upsert_tag_translation(
        conn,
        payload.tag_id,
        payload.language,
        payload.content,
    )
    await conn.commit()
    return TagTranslationItem(
        tag_id=payload.tag_id,
        tag_name=tag["name"],
        type=tag["type"],
        sub_type=tag["sub_type"],
        language=payload.language,
        content=payload.content,
    )


@router.put("/{tag_id}/{language}", response_model=TagTranslationItem)
async def update(
    tag_id: int,
    language: str,
    payload: TagTranslationUpdate,
    *,
    conn: DBConnection,
) -> TagTranslationItem:
    """Update the content of an existing tag translation."""
    tag = await core.get_tag_by_id(conn, tag_id)
    if tag is None:
        raise HTTPException(status_code=404, detail="标签不存在")
    if not await core.update_tag_translation(conn, tag_id, language, payload.content):
        raise HTTPException(status_code=404, detail="翻译不存在")
    await conn.commit()
    return TagTranslationItem(
        tag_id=tag_id,
        tag_name=tag["name"],
        type=tag["type"],
        sub_type=tag["sub_type"],
        language=language,
        content=payload.content,
    )


@router.delete("/{tag_id}/{language}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(
    tag_id: int,
    language: str,
    *,
    conn: DBConnection,
) -> Response:
    """Delete a tag translation by its natural key."""
    if not await core.delete_tag_translation(conn, tag_id, language):
        raise HTTPException(status_code=404, detail="翻译不存在")
    await conn.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/batch", response_model=BatchImportResult)
async def batch_import(
    payload: BatchImportRequest,
    *,
    conn: DBConnection,
) -> BatchImportResult:
    """Batch upsert translations by tag name."""
    stats = await core.batch_upsert_tag_translations(
        conn,
        [entry.model_dump() for entry in payload.entries],
    )
    await conn.commit()
    return BatchImportResult(updated=stats["updated"], missing=stats["missing"])
