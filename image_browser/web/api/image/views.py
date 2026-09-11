import json
from io import BytesIO
from pathlib import Path
from typing import Any, cast

import numpy as np
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from numpy.typing import NDArray
from psycopg import errors as pg_errors
from starlette.concurrency import run_in_threadpool

from image_browser.db import core
from image_browser.db.dependencies import DBConnection
from image_browser.db.models.image import Image
from image_browser.settings import settings
from image_browser.utils.image import ImageProcessor
from image_browser.web.api.image.schema import (
    ImageCreate,
    ImageDetail,
    ImageListItem,
    ImageListResponse,
    ImageTagItem,
    UploadResult,
)
from image_browser.web.api.language import Language
from image_browser.web.api.pagination import Paginator, calc_total_pages

router = APIRouter()

# Shared album directory: project-root/images/<first-two-signature-chars>/<sig>.<ext>.
IMAGES_DIR = settings.images_dir_path


def _build_list_response(
    items: list[dict[str, Any]],
    total: int,
    page: int,
    per_page: int,
) -> ImageListResponse:
    """Build a unified paginated list response."""
    return ImageListResponse(
        items=[ImageListItem.model_validate(item) for item in items],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=calc_total_pages(total, per_page),
    )


def _parse_signature(value: str) -> bytes:
    """Parse a hex signature string into bytes."""
    try:
        return bytes.fromhex(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="签名必须是十六进制字符串") from exc


def _to_image_model(payload: ImageCreate, signature: bytes) -> Image:
    """Convert an API create payload into a database model."""
    return Image(
        width=payload.width,
        height=payload.height,
        format=payload.format,
        filesize=payload.filesize,
        signature=signature,
        fingerprint=payload.fingerprint,
        filename=payload.filename,
        filepath=payload.filepath,
    )


def _to_image_data(payload: ImageCreate, signature: bytes) -> dict[str, object]:
    """Convert an API create payload into an update column dict."""
    return {
        "width": payload.width,
        "height": payload.height,
        "format": payload.format,
        "filesize": payload.filesize,
        "signature": signature,
        "fingerprint": payload.fingerprint,
        "filename": payload.filename,
        "filepath": payload.filepath,
    }


def _safe_relpath(raw: str) -> str | None:
    """Normalize a relative path and reject path traversal."""
    path = Path(raw.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        return None
    return path.as_posix()


def _parse_image_bytes(raw: bytes) -> dict[str, object] | None:
    """Parse image bytes with the local model; None if not a valid image."""
    try:
        processor = ImageProcessor.open_image(BytesIO(raw))
    except Exception:
        return None
    generals, characters, series = processor.extract_tags()
    return {
        **processor.get_metadata(),
        "generals": generals,
        "characters": characters,
        "series": series,
    }


# Tag type weights used by the hybrid search (tuned in backend code only).
TAG_TYPE_WEIGHTS: dict[str, float] = json.loads(settings.search_tag_type_weights)


def _parse_fp_vector(value: object) -> NDArray[np.float32] | None:
    """Parse a stored fingerprint (text JSON / list / pgvector Vector)."""
    if value is None:
        return None
    try:
        if isinstance(value, str):
            value = json.loads(value)
        elif hasattr(value, "to_list"):
            value = value.to_list()
        elif not isinstance(value, (list, tuple, np.ndarray)):
            value = json.loads(str(value))
        return cast(NDArray[np.float32], np.asarray(value, dtype=np.float32))
    except (TypeError, ValueError):
        return None


def _score_images(
    rows: list[dict[str, object]],
    target_vec: NDArray[np.float32],
    tag_scores: dict[str, dict[int, float]],
    *,
    fp_w: float,
    tg_w: float,
    tag_type_weights: dict[str, float],
    fp_threshold: float,
) -> list[tuple[float, int]]:
    """Score images by fingerprint similarity and type-weighted tags."""
    scored: list[tuple[float, int]] = []
    for row in rows:
        vec = _parse_fp_vector(row.get("fingerprint"))
        sim_fp = 0.0
        if vec is not None:
            sim_fp = max(0.0, min(1.0, float(np.dot(vec, target_vec))))
            if sim_fp < fp_threshold:
                sim_fp = 0.0
        sim_tag = 0.0
        image_id = cast(int, row["id"])
        for tag_type, weight in tag_type_weights.items():
            type_scores = tag_scores.get(tag_type, {})
            max_type_score = max(type_scores.values(), default=1.0)
            sim_tag += weight * type_scores.get(image_id, 0.0) / max_type_score
        score = fp_w * sim_fp + tg_w * sim_tag
        if score > 0:
            scored.append((score, image_id))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return scored


@router.get("", response_model=ImageListResponse)
async def index(
    paginator: Paginator,
    language: Language,
    *,
    conn: DBConnection,
) -> ImageListResponse:
    """List images with tags in pages."""
    items, total = await core.list_images_with_tags(
        conn,
        paginator.offset,
        paginator.limit,
        language,
    )
    return _build_list_response(items, total, paginator.page, paginator.per_page)


@router.post("", response_model=ImageDetail, status_code=status.HTTP_201_CREATED)
async def create_image_item(
    payload: ImageCreate,
    *,
    conn: DBConnection,
) -> ImageDetail:
    """Create a new image record."""
    signature = _parse_signature(payload.signature)
    try:
        image_id = await core.create_image(
            conn,
            _to_image_model(payload, signature),
        )
    except pg_errors.UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="签名已存在") from exc
    await conn.commit()
    data = await core.get_image_detail(conn, image_id)
    if data is None:
        raise HTTPException(status_code=500, detail="创建后数据缺失")
    return ImageDetail(**data)


@router.post("/search-by-image", response_model=ImageListResponse)
async def search_by_image(
    file: UploadFile = File(...),
    language: Language = "zh",
    *,
    conn: DBConnection,
) -> ImageListResponse:
    """Hybrid image search by perceptual fingerprint and model tags."""
    raw = await file.read()
    await file.close()
    try:
        parsed = await run_in_threadpool(_parse_image_bytes, raw)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="图片解析失败") from exc
    if parsed is None:
        raise HTTPException(status_code=400, detail="无法识别的图片")

    weight_sum = settings.search_fingerprint_weight + settings.search_tag_weight
    if weight_sum <= 0:
        raise HTTPException(status_code=400, detail="权重之和必须大于 0")
    fp_w = settings.search_fingerprint_weight / weight_sum
    tg_w = settings.search_tag_weight / weight_sum

    images = await core.list_image_fingerprints(conn)
    target_vec = np.asarray(parsed["fingerprint"], dtype=np.float32)
    tag_names: list[str] = [
        name
        for name, score in {
            **cast(dict[str, float], parsed["characters"]),
            **cast(dict[str, float], parsed["series"]),
        }.items()
        if score >= settings.search_tag_score_threshold
    ]
    tag_ids = await core.get_tag_ids_by_names(conn, tag_names)
    tag_scores = await core.list_image_tag_scores(conn, tag_ids)

    scored = _score_images(
        images,
        target_vec,
        tag_scores,
        fp_w=fp_w,
        tg_w=tg_w,
        tag_type_weights=TAG_TYPE_WEIGHTS,
        fp_threshold=settings.search_fingerprint_threshold,
    )
    top_ids = [image_id for _, image_id in scored[:24]]

    items = await core.list_images_by_ids(conn, top_ids, language)
    per_page = len(items) or 1
    return ImageListResponse(
        items=[ImageListItem.model_validate(item) for item in items],
        total=len(items),
        page=1,
        per_page=per_page,
        total_pages=calc_total_pages(len(items), per_page),
    )


@router.get("/search", response_model=ImageListResponse)
async def search(
    query: str,
    paginator: Paginator,
    language: Language,
    *,
    conn: DBConnection,
) -> ImageListResponse:
    """Full-text search images with weighted tags."""
    items, total = await core.search_images_with_tags(
        conn,
        query,
        paginator.offset,
        paginator.limit,
        language,
    )
    return _build_list_response(items, total, paginator.page, paginator.per_page)


@router.post("/upload", response_model=list[UploadResult])
async def upload_images(
    files: list[UploadFile] = File(...),
    *,
    conn: DBConnection,
) -> list[UploadResult]:
    """Upload image files, parse with the local model, and insert into DB."""
    results: list[UploadResult] = []
    for upload in files:
        relpath = _safe_relpath(upload.filename or "")
        if relpath is None:
            results.append(
                UploadResult(
                    filename=upload.filename or "",
                    status="error",
                    message="非法路径",
                ),
            )
            await upload.close()
            continue
        raw = await upload.read()
        await upload.close()
        try:
            parsed = await run_in_threadpool(_parse_image_bytes, raw)
        except Exception:
            results.append(
                UploadResult(
                    filename=Path(relpath).name,
                    status="error",
                    message="解析失败",
                ),
            )
            continue
        if parsed is None:
            results.append(
                UploadResult(
                    filename=Path(relpath).name,
                    status="error",
                    message="无法识别的图片",
                ),
            )
            continue
        existing = await core.get_image_by_signature(conn, cast(bytes, parsed["signature"]))
        if existing is not None:
            results.append(
                UploadResult(
                    filename=Path(relpath).name,
                    status="skipped",
                    message="签名已存在",
                ),
            )
            continue
        # Store by signature hash: images/<sig[:2]>/<sig><ext>; filepath keeps
        # the relative path (relative to the images dir), filename the source
        # file name.
        sig = cast(bytes, parsed["signature"]).hex()
        ext = Path(relpath).suffix or "." + str(parsed["format"]).lower()
        sub_dir = sig[:2]
        stored_name = sig + ext
        target = IMAGES_DIR / sub_dir / stored_name
        target.parent.mkdir(parents=True, exist_ok=True)
        await run_in_threadpool(target.write_bytes, raw)
        image = Image(
            width=cast(int, parsed["width"]),
            height=cast(int, parsed["height"]),
            format=cast(str, parsed["format"]),
            filesize=cast(int, parsed["filesize"]),
            signature=cast(bytes, parsed["signature"]),
            fingerprint=cast(list[float], parsed["fingerprint"]),
            filename=Path(relpath).name,
            filepath=f"{sub_dir}/{stored_name}",
        )
        try:
            image_id = await core.create_image(conn, image)
            await core.set_image_tags(
                conn,
                image_id,
                list(cast(dict[str, float], parsed["generals"]).items()),
                list(cast(dict[str, float], parsed["characters"]).items()),
                list(cast(dict[str, float], parsed["series"]).items()),
            )
        except pg_errors.UniqueViolation:
            results.append(
                UploadResult(
                    filename=Path(relpath).name,
                    status="skipped",
                    message="签名已存在",
                ),
            )
            continue
        results.append(
            UploadResult(
                filename=Path(relpath).name,
                status="created",
                image_id=image_id,
                message="已入库",
            ),
        )
    await conn.commit()
    return results


@router.get("/{image_id}", response_model=ImageDetail)
async def get_image(
    image_id: int,
    language: Language,
    *,
    conn: DBConnection,
) -> ImageDetail:
    """Get single image detail with tags and raw scores."""
    data = await core.get_image_detail(conn, image_id, language)
    if data is None:
        raise HTTPException(status_code=404, detail="图片不存在")
    return ImageDetail(**data)


@router.put("/{image_id}", response_model=ImageDetail)
async def replace_image_item(
    image_id: int,
    payload: ImageCreate,
    *,
    conn: DBConnection,
) -> ImageDetail:
    """Replace an image record entirely."""
    signature = _parse_signature(payload.signature)
    try:
        updated = await core.update_image(
            conn,
            image_id,
            _to_image_data(payload, signature),
        )
    except pg_errors.UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="签名已存在") from exc
    if not updated:
        raise HTTPException(status_code=404, detail="图片不存在")
    await conn.commit()
    data = await core.get_image_detail(conn, image_id)
    if data is None:
        raise HTTPException(status_code=500, detail="更新后数据缺失")
    return ImageDetail(**data)


@router.delete("/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_image_item(
    image_id: int,
    *,
    conn: DBConnection,
) -> Response:
    """Delete an image record (tag relations cascade)."""
    deleted = await core.delete_image(conn, image_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="图片不存在")
    await conn.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{image_id}/tag", response_model=list[ImageTagItem])
async def get_image_tags(
    image_id: int,
    *,
    conn: DBConnection,
) -> list[ImageTagItem]:
    """Get raw tags with confidence scores of an image."""
    data = await core.get_image_detail(conn, image_id)
    if data is None:
        raise HTTPException(status_code=404, detail="图片不存在")
    return [
        ImageTagItem(
            id=item["id"],
            type=item["type"],
            name=item["name"],
            score=item["score"],
        )
        for tag_list in data["scores"].values()
        for item in tag_list
    ]
