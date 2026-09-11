import json
from typing import Any

import psycopg
from psycopg import rows, sql
from psycopg.rows import dict_row

from image_browser.settings import settings

from .models.image import Image, Tag, TagTarn, TagType


async def create_image(conn: psycopg.AsyncConnection, image: Image) -> int:
    """Create an image record and return its id."""
    async with conn.cursor() as cur:
        await cur.execute(
            """
INSERT INTO image (
    width,
    height,
    format,
    filesize,
    signature,
    fingerprint,
    filename,
    filepath
)
VALUES (
    %(width)s,
    %(height)s,
    %(format)s,
    %(filesize)s,
    %(signature)s,
    %(fingerprint)s,
    %(filename)s,
    %(filepath)s
)
RETURNING id
        """,
            {
                **image.model_dump(exclude={"signature"}),
                "signature": image.signature,
            },
        )
        row = await cur.fetchone()
        if row is None:
            raise RuntimeError("INSERT 未返回 id")
        return row[0]


async def get_image_by_id(conn: psycopg.AsyncConnection, image_id: int) -> Image | None:
    """Get a single image by id."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT * FROM image WHERE id = %(id)s LIMIT 1",
            {
                "id": image_id,
            },
        )
        row = await cur.fetchone()
        if row:
            row.update({"fingerprint": json.loads(row["fingerprint"])})
            return Image(
                **row,
            )
        return None


async def get_image_by_signature(
    conn: psycopg.AsyncConnection,
    signature: bytes,
) -> Image | None:
    """Get a single image by its perceptual signature."""
    async with conn.cursor(row_factory=rows.class_row(Image)) as cur:
        await cur.execute(
            "SELECT * FROM image WHERE signature = %(signature)s::bytea LIMIT 1",
            {
                "signature": signature,
            },
        )
        return await cur.fetchone()


async def get_images(
    conn: psycopg.AsyncConnection,
    offset: int = 0,
    limit: int = 10,
) -> list[Image]:
    """Get images in a page."""
    async with conn.cursor(row_factory=rows.class_row(Image)) as cur:
        await cur.execute(
            "SELECT * FROM image LIMIT %(limit)s OFFSET %(offset)s",
            {
                "limit": limit,
                "offset": offset,
            },
        )
        return await cur.fetchall()


async def update_image(
    conn: psycopg.AsyncConnection,
    image_id: int,
    image_data: dict[str, Any],
) -> bool:
    """Partially update image fields from a dict of column values."""
    if not image_data:
        return False
    set_clause = sql.SQL(", ").join(sql.SQL("{} = %s").format(sql.Identifier(name)) for name in image_data)
    params = [*image_data.values(), image_id]
    async with conn.cursor() as cur:
        await cur.execute(
            sql.SQL("UPDATE image SET {} WHERE id = %s").format(set_clause),
            params,
        )
        return cur.rowcount > 0


async def delete_image(conn: psycopg.AsyncConnection, image_id: int) -> bool:
    """Delete an image row by id.

    Tag relations are removed explicitly first: the AFTER DELETE trigger on
    image_tag_assoc rebuilds translation rows while the image row still
    exists, otherwise the cascade-triggered rebuild would violate the
    image_tag foreign key.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            "DELETE FROM image_tag_assoc WHERE image_id = %s",
            (image_id,),
        )
        await cur.execute(
            "DELETE FROM image WHERE id = %s",
            (image_id,),
        )
        return cur.rowcount > 0


async def bulk_insert_tags(conn: psycopg.AsyncConnection, tags: list[Tag]) -> None:
    """Bulk insert tags into the directory (idempotent)."""
    async with conn.cursor() as cur:
        await cur.executemany(
            """
INSERT INTO tag (type, name) VALUES (%(type)s, %(name)s)
ON CONFLICT (type, name) DO NOTHING
            """,
            [tag.model_dump() for tag in tags],
        )


async def bulk_insert_tags_tarn(
    conn: psycopg.AsyncConnection,
    tags: list[TagTarn],
) -> None:
    """Bulk insert tag translations (idempotent)."""
    async with conn.cursor() as cur:
        await cur.executemany(
            """
INSERT INTO tag_tarn (tag_id, type, language, content)
VALUES (%(tag_id)s, %(type)s, %(language)s, %(content)s)
ON CONFLICT (tag_id, type, language) DO NOTHING
            """,
            [tag.model_dump() for tag in tags],
        )


# 批量设置标签：先清除原有关联，再插入新关联
async def set_image_tags(
    conn: psycopg.AsyncConnection,
    image_id: int,
    general_tags: list[tuple[str, float]],
    character_tags: list[tuple[str, float]],
    series_tags: list[tuple[str, float]],
) -> None:
    """Set image tags wholesale and rebuild the image_tag cache row."""
    items = []
    for name, score in general_tags:
        items.append((image_id, name, TagType.GENERAL, score))
    for name, score in character_tags:
        items.append((image_id, name, TagType.CHARACTER_NAME, score))
    for name, score in series_tags:
        items.append((image_id, name, TagType.COPYRIGHT, score))

    if not items:
        # 空标签，只删除旧关联
        stmt = sql.SQL("DELETE FROM image_tag_assoc WHERE image_id = %s")
        async with conn.cursor() as cur:
            await cur.execute(stmt, (image_id,))
        return

    # ========== 手动生成VALUES占位符 ==========
    row_placeholder = sql.SQL("(%s, %s, %s::tag_type, %s)")
    row_placeholders = sql.SQL(", ").join(row_placeholder for _ in items)
    params: list[Any] = []
    for r in items:
        params.extend(r)

    cte_sql = sql.SQL(
        """
WITH old_clean AS (
    DELETE FROM image_tag_assoc WHERE image_id = %s
),
input_data(image_id, tag_name, tag_type, score) AS (
    VALUES {row_placeholders}
),
tag_upsert AS (
    INSERT INTO tag (type, name)
    SELECT
        tag_type,
        tag_name
    FROM input_data
    ON CONFLICT (type, name)
    DO UPDATE SET
        name = EXCLUDED.name
    RETURNING id, type, name
)
INSERT INTO
    image_tag_assoc (image_id, tag_id, type, score)
SELECT
    d.image_id, t.id, t.type, d.score
FROM
    input_data d
JOIN
    tag_upsert t ON t.type = d.tag_type AND t.name = d.tag_name
ON CONFLICT (image_id, tag_id) DO NOTHING;
        """,
    ).format(
        row_placeholders=row_placeholders,
    )

    # 第一个参数是image_id（old_clean的WHERE）
    full_params = [image_id, *params]

    async with conn.cursor() as cur:
        await cur.execute(cte_sql, full_params)
        # 同步重建 image_tag 缓存行（列表聚合与全文搜索依赖此表）。
        await cur.execute(
            """
WITH agg AS (
    SELECT
        ita.image_id,
        COALESCE(array_agg(t.name ORDER BY ita.score DESC)
            FILTER (WHERE t.type = 'CHARACTER_NAME'::tag_type), '{}') AS characters,
        COALESCE(array_agg(t.name ORDER BY ita.score DESC)
            FILTER (WHERE t.type = 'COPYRIGHT'::tag_type), '{}') AS series,
        COALESCE(array_agg(t.name ORDER BY ita.score DESC)
            FILTER (WHERE t.type = 'GENERAL'::tag_type), '{}') AS tags
    FROM image_tag_assoc ita
    JOIN tag t ON ita.tag_id = t.id
    WHERE ita.image_id = %s
    GROUP BY ita.image_id
)
INSERT INTO image_tag (image_id, language, characters, series, tags)
SELECT image_id, 'en', characters, series, tags FROM agg
ON CONFLICT (image_id, language) DO UPDATE SET
    characters = EXCLUDED.characters,
    series = EXCLUDED.series,
    tags = EXCLUDED.tags,
    modified_at = now()
            """,
            (image_id,),
        )


# -------------------- 搜索 API --------------------
async def search_text(
    conn: psycopg.AsyncConnection,
    query: str,
    offset: int = 0,
    limit: int = 10,
    *,
    weights: list[int] | None = None,
) -> tuple[list[Image], int]:
    """Full-text search based on the image_tag cache table."""
    if weights is None:
        weights = settings.search_fulltext_weights

    async with conn.cursor(row_factory=rows.class_row(Image)) as cur:
        await cur.execute(
            """
SELECT
    i.id,
    i.width,
    i.height,
    i.format,
    i.filesize,
    i.signature,
    i.fingerprint,
    i.filename,
    i.filepath,
    i.filename,
    it.characters,
    it.series,
    it.tags,
    i.created_at,
    i.modified_at,
    (
        CASE WHEN it.characters &@~ %(query)s THEN %(characters_weight)s ELSE 0 END +
        CASE WHEN it.series &@~ %(query)s THEN %(series_weight)s ELSE 0 END +
        CASE WHEN it.tags &@~ %(query)s THEN %(tags_weight)s ELSE 0 END
    ) AS score
FROM
    image_tag it
JOIN
    image i ON it.image_id = i.id
WHERE
    it.characters &@~ %(query)s
    OR it.series &@~ %(query)s
    OR it.tags &@~ %(query)s
ORDER BY
    score DESC
LIMIT
    %(limit)s
OFFSET
    %(offset)s
        """,
            {
                "query": query,
                "characters_weight": weights[0],
                "series_weight": weights[1],
                "tags_weight": weights[2],
                "limit": limit,
                "offset": offset,
            },
        )
        items = await cur.fetchall()

    async with conn.cursor(row_factory=rows.dict_row) as cur:
        await cur.execute(
            """
SELECT
    count(*) AS total
FROM
    image_tag it
JOIN
    image i ON it.image_id = i.id
WHERE
    it.characters &@~ %(query)s
    OR it.series &@~ %(query)s
    OR it.tags &@~ %(query)s
            """,
            {
                "query": query,
            },
        )
        row = await cur.fetchone()
        if row is None:
            raise RuntimeError("count 查询失败")
        total = row["total"]

    return items, total


async def _load_tag_translations(
    conn: psycopg.AsyncConnection,
    names: set[str],
    language: str,
) -> dict[str, str]:
    """Build a translated-content map for one language.

    Keys include both the raw tag name and the English translation, because
    stored tag arrays may hold either form.
    """
    if not names:
        return {}
    async with conn.cursor() as cur:
        await cur.execute(
            """
SELECT t.name, tt.content, tten.content AS en_content
FROM tag t
JOIN tag_translation tt
    ON tt.tag_id = t.id AND tt.language = %(language)s
LEFT JOIN tag_translation tten
    ON tten.tag_id = t.id AND tten.language = 'en'
WHERE t.name = ANY(%(names)s)
   OR tten.content = ANY(%(names)s)
            """,
            {"language": language, "names": list(names)},
        )
        rows = await cur.fetchall()
    mapping: dict[str, str] = {}
    for name, content, en_content in rows:
        if content is None or name in mapping:
            continue
        mapping[name] = content
        if en_content:
            mapping.setdefault(en_content, content)
    return mapping


async def _translate_arrays(
    conn: psycopg.AsyncConnection,
    rows: list[dict[str, Any]],
    language: str,
) -> None:
    """Translate tag-name arrays/scores of each row in place.

    Arrays prefer the requested language and fall back to the English
    translation, then to the raw name. Score contents keep the requested
    language only (None when missing) so admin panels stay stable.
    """
    if not rows:
        return
    names = _collect_tag_names(rows)
    current = await _load_tag_translations(conn, names, language)
    array_mapping = dict(current)
    if language != "en":
        missing = names - set(array_mapping)
        if missing:
            array_mapping.update(await _load_tag_translations(conn, missing, "en"))
    for row in rows:
        _translate_row(row, array_mapping, current)


def _collect_tag_names(rows: list[dict[str, Any]]) -> set[str]:
    """Collect every tag name referenced by the rows."""
    names: set[str] = set()
    for row in rows:
        for key in ("characters", "series", "tags"):
            names.update(row.get(key) or [])
        for group in (row.get("scores") or {}).values():
            for tag in group:
                names.add(tag["name"])
    return names


def _translate_row(
    row: dict[str, Any],
    array_mapping: dict[str, str],
    content_mapping: dict[str, str],
) -> None:
    """Apply name mappings to arrays and scores of one row in place."""
    for key in ("characters", "series", "tags"):
        row[key] = [array_mapping.get(name, name) for name in (row.get(key) or [])]
    for group in (row.get("scores") or {}).values():
        for tag in group:
            tag["content"] = content_mapping.get(tag["name"])


async def list_images_with_tags(
    conn: psycopg.AsyncConnection,
    offset: int = 0,
    limit: int = 10,
    language: str = "en",
) -> tuple[list[dict[str, Any]], int]:
    """
    List images with tags of current language (en) in pages.

    :return: (rows, total), each row contains characters/series/tags arrays
        and aggregated scores.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
WITH img_score_rows AS (
    SELECT
        ita.image_id,
        t.type,
        jsonb_agg(
            jsonb_build_object('id', ita.tag_id, 'score', ita.score, 'name', t.name)
            ORDER BY ita.score DESC
        ) AS tag_list
    FROM image_tag_assoc ita
    JOIN tag t ON ita.tag_id = t.id
    GROUP BY ita.image_id, t.type
),
img_scores AS (
    SELECT image_id, jsonb_object_agg(type, tag_list) AS scores
    FROM img_score_rows
    GROUP BY image_id
)
SELECT
    i.id,
    i.width,
    i.height,
    i.format,
    i.filesize,
    i.filename,
    i.filepath,
    i.created_at,
    i.modified_at,
    COALESCE(it.characters, '{}') AS characters,
    COALESCE(it.series, '{}') AS series,
    COALESCE(it.tags, '{}') AS tags,
    COALESCE(s.scores, '{}'::jsonb) AS scores
FROM image i
LEFT JOIN image_tag it ON it.image_id = i.id AND it.language = 'en'
LEFT JOIN img_scores s ON s.image_id = i.id
ORDER BY i.id
LIMIT %(limit)s OFFSET %(offset)s
            """,
            {
                "limit": limit,
                "offset": offset,
            },
        )
        items = await cur.fetchall()

        await cur.execute("SELECT count(*) AS total FROM image")
        row = await cur.fetchone()
        if row is None:
            raise RuntimeError("count 查询失败")
        total = row["total"]

    await _translate_arrays(conn, items, language)

    return items, total


async def _translate_query_to_names(
    conn: psycopg.AsyncConnection,
    query: str,
) -> list[str]:
    """Reverse-lookup Chinese query to English tag names via translations."""
    async with conn.cursor() as cur:
        await cur.execute(
            """
SELECT DISTINCT t.name
FROM tag_translation tt
JOIN tag t ON t.id = tt.tag_id
WHERE tt.language = 'zh'
  AND tt.content ILIKE %(like)s
ORDER BY t.name
LIMIT 50
            """,
            {"like": f"%{query}%"},
        )
        return [row[0] for row in await cur.fetchall()]


def _build_search_query(query: str, translated_names: list[str]) -> str:
    """Rebuild pgroonga query, preferring translated English tag names."""
    if not translated_names:
        return query
    return " OR ".join('"' + name.replace('"', '""') + '"' for name in translated_names)


async def search_images_with_tags(
    conn: psycopg.AsyncConnection,
    query: str,
    offset: int = 0,
    limit: int = 10,
    language: str = "en",
    *,
    weights: list[int] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """
    Full-text search images (based on image_tag cache table) with tags.

    weights: [character weight, series weight, tag weight]
    :return: (rows, total), each row contains characters/series/tags arrays
        and the match score.
    """
    if weights is None:
        weights = settings.search_fulltext_with_tags_weights

    # 中文查询经 tag_translation 反查英文标签名（image_tag 缓存只存英文）
    translated_names = await _translate_query_to_names(conn, query)
    query = _build_search_query(query, translated_names)

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
WITH matched AS (
    SELECT
        it.image_id,
        (
            CASE
                WHEN it.characters &@~ %(query)s THEN %(characters_weight)s ELSE 0
            END +
            CASE
                WHEN it.series &@~ %(query)s THEN %(series_weight)s ELSE 0
            END +
            CASE
                WHEN it.tags &@~ %(query)s THEN %(tags_weight)s ELSE 0
            END
        ) AS score
    FROM image_tag it
    WHERE it.characters &@~ %(query)s
       OR it.series &@~ %(query)s
       OR it.tags &@~ %(query)s
)
SELECT
    i.id,
    i.width,
    i.height,
    i.format,
    i.filesize,
    i.filename,
    i.filepath,
    i.created_at,
    i.modified_at,
    COALESCE(it2.characters, '{}') AS characters,
    COALESCE(it2.series, '{}') AS series,
    COALESCE(it2.tags, '{}') AS tags,
    m.score
FROM matched m
JOIN image i ON i.id = m.image_id
LEFT JOIN image_tag it2 ON it2.image_id = m.image_id AND it2.language = 'en'
ORDER BY m.score DESC, i.id
LIMIT %(limit)s OFFSET %(offset)s
            """,
            {
                "query": query,
                "characters_weight": weights[0],
                "series_weight": weights[1],
                "tags_weight": weights[2],
                "limit": limit,
                "offset": offset,
            },
        )
        items = await cur.fetchall()

        await cur.execute(
            """
SELECT count(*) AS total
FROM image_tag it
WHERE it.characters &@~ %(query)s
   OR it.series &@~ %(query)s
   OR it.tags &@~ %(query)s
            """,
            {
                "query": query,
            },
        )
        row = await cur.fetchone()
        if row is None:
            raise RuntimeError("count 查询失败")
        total = row["total"]

    await _translate_arrays(conn, items, language)

    return items, total


async def list_image_fingerprints(
    conn: psycopg.AsyncConnection,
) -> list[dict[str, Any]]:
    """List image ids, filenames and DCT fingerprint vectors."""
    async with conn.cursor(row_factory=rows.dict_row) as cur:
        await cur.execute(
            "SELECT id, filename, fingerprint FROM image ORDER BY id",
        )
        return await cur.fetchall()


async def get_tag_ids_by_names(
    conn: psycopg.AsyncConnection,
    names: list[str],
) -> list[int]:
    """Resolve tag directory names into tag ids."""
    if not names:
        return []
    async with conn.cursor(row_factory=rows.dict_row) as cur:
        await cur.execute(
            "SELECT id FROM tag WHERE name = ANY(%(names)s)",
            {"names": names},
        )
        return [row["id"] for row in await cur.fetchall()]


async def list_image_tag_scores(
    conn: psycopg.AsyncConnection,
    tag_ids: list[int],
) -> dict[str, dict[int, float]]:
    """Sum per-image tag confidence grouped by tag type."""
    if not tag_ids:
        return {}
    async with conn.cursor(row_factory=rows.dict_row) as cur:
        await cur.execute(
            """
SELECT ita.type, ita.image_id, SUM(ita.score) AS tag_score
FROM image_tag_assoc ita
WHERE ita.tag_id = ANY(%(tag_ids)s)
GROUP BY ita.type, ita.image_id
            """,
            {"tag_ids": tag_ids},
        )
        grouped: dict[str, dict[int, float]] = {}
        for row in await cur.fetchall():
            grouped.setdefault(row["type"], {})[row["image_id"]] = float(
                row["tag_score"],
            )
        return grouped


async def list_images_by_ids(
    conn: psycopg.AsyncConnection,
    image_ids: list[int],
    language: str = "en",
) -> list[dict[str, Any]]:
    """List images in the given id order with their tags translated."""
    if not image_ids:
        return []
    async with conn.cursor(row_factory=rows.dict_row) as cur:
        await cur.execute(
            """
WITH img_score_rows AS (
    SELECT
        ita.image_id,
        t.type,
        jsonb_agg(
            jsonb_build_object('id', ita.tag_id, 'score', ita.score, 'name', t.name)
            ORDER BY ita.score DESC
        ) AS tag_list
    FROM image_tag_assoc ita
    JOIN tag t ON ita.tag_id = t.id
    GROUP BY ita.image_id, t.type
),
img_scores AS (
    SELECT image_id, jsonb_object_agg(type, tag_list) AS scores
    FROM img_score_rows
    GROUP BY image_id
)
SELECT
    i.id,
    i.width,
    i.height,
    i.format,
    i.filesize,
    i.filename,
    i.filepath,
    i.created_at,
    i.modified_at,
    COALESCE(it.characters, '{}') AS characters,
    COALESCE(it.series, '{}') AS series,
    COALESCE(it.tags, '{}') AS tags,
    COALESCE(s.scores, '{}'::jsonb) AS scores
FROM image i
LEFT JOIN image_tag it ON it.image_id = i.id AND it.language = 'en'
LEFT JOIN img_scores s ON s.image_id = i.id
WHERE i.id = ANY(%(ids)s)
ORDER BY array_position(%(ids)s, i.id)
            """,
            {"ids": image_ids},
        )
        items = await cur.fetchall()
    await _translate_arrays(conn, items, language)
    return items


async def get_image_detail(
    conn: psycopg.AsyncConnection,
    image_id: int,
    language: str = "en",
) -> dict[str, Any] | None:
    """
    Get single image detail (with translated tags and raw tag scores).

    :return: row dict (signature as hex string, fingerprint as list),
        or None if the image does not exist.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
SELECT
    i.id,
    i.width,
    i.height,
    i.format,
    i.filesize,
    encode(i.signature, 'hex') AS signature,
    i.fingerprint::text AS fingerprint,
    i.filename,
    i.filepath,
    i.created_at,
    i.modified_at,
    COALESCE(it.characters, '{}') AS characters,
    COALESCE(it.series, '{}') AS series,
    COALESCE(it.tags, '{}') AS tags
FROM image i
LEFT JOIN image_tag it ON it.image_id = i.id AND it.language = 'en'
WHERE i.id = %(image_id)s
            """,
            {
                "image_id": image_id,
            },
        )
        row = await cur.fetchone()
        if row is None:
            return None

        row["fingerprint"] = json.loads(row["fingerprint"])

        await cur.execute(
            """
SELECT
    t.id,
    t.type,
    t.name,
    ita.score
FROM image_tag_assoc ita
JOIN tag t ON ita.tag_id = t.id
WHERE ita.image_id = %(image_id)s
ORDER BY t.type, ita.score DESC
            """,
            {
                "image_id": image_id,
            },
        )
        tag_rows = await cur.fetchall()

    scores: dict[str, list[dict[str, Any]]] = {}
    for tag in tag_rows:
        scores.setdefault(tag["type"], []).append(tag)
    row["scores"] = scores
    await _translate_arrays(conn, [row], language)

    return row


# -------------------- 标签翻译管理 API --------------------


async def list_tag_translations(
    conn: psycopg.AsyncConnection,
    query: str = "",
    offset: int = 0,
    limit: int = 12,
    *,
    tag_type: str | None = None,
    sub_type: str | None = None,
    language: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """List tag translations joined with the tag directory."""
    conds: list[str] = []
    params: list[Any] = []
    if query:
        conds.append("(t.name ILIKE %s OR tt.content ILIKE %s OR tt.language ILIKE %s)")
        like = f"%{query}%"
        params += [like, like, like]
    if tag_type:
        conds.append("t.type::text = %s")
        params.append(tag_type)
    if sub_type:
        conds.append("t.sub_type::text = %s")
        params.append(sub_type)
    if language:
        conds.append("tt.language = %s")
        params.append(language)
    where_clause = sql.SQL("WHERE " + " AND ".join(conds)) if conds else sql.SQL("")
    base_sql = sql.SQL(
        """
FROM tag_translation tt
JOIN tag t ON t.id = tt.tag_id
{where}
        """,
    ).format(where=where_clause)
    async with conn.cursor(row_factory=rows.dict_row) as cur:
        await cur.execute(sql.SQL("SELECT count(*) AS count ") + base_sql, params)
        row = await cur.fetchone()
        if row is None:
            raise RuntimeError("count 查询失败")
        total = row["count"]
        await cur.execute(
            sql.SQL(
                """
SELECT tt.tag_id, t.type, t.sub_type, tt.language, tt.content, t.name AS tag_name
{base}
ORDER BY tt.tag_id, tt.language
LIMIT %s OFFSET %s
                """,
            ).format(base=base_sql),
            [*params, limit, offset],
        )
        items = await cur.fetchall()
    return items, total


async def list_missing_tag_translations(
    conn: psycopg.AsyncConnection,
    query: str = "",
    offset: int = 0,
    limit: int = 12,
    *,
    tag_type: str | None = None,
    sub_type: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """List tags that have no translation row (regardless of image usage)."""
    conds: list[str] = ["tt.tag_id IS NULL"]
    params: list[Any] = []
    if query:
        conds.append("(t.name ILIKE %s OR t.type::text ILIKE %s)")
        like = f"%{query}%"
        params += [like, like]
    if tag_type:
        conds.append("t.type::text = %s")
        params.append(tag_type)
    if sub_type:
        conds.append("t.sub_type::text = %s")
        params.append(sub_type)
    where_clause = sql.SQL("WHERE " + " AND ".join(conds))
    base_sql = sql.SQL(
        """
FROM tag t
LEFT JOIN tag_translation tt ON tt.tag_id = t.id
{where}
        """,
    ).format(where=where_clause)
    async with conn.cursor(row_factory=rows.dict_row) as cur:
        await cur.execute(sql.SQL("SELECT count(*) AS count ") + base_sql, params)
        row = await cur.fetchone()
        if row is None:
            raise RuntimeError("count 查询失败")
        total = row["count"]
        await cur.execute(
            sql.SQL(
                """
SELECT t.id AS tag_id, t.name AS tag_name, t.type, t.sub_type
{base}
ORDER BY t.type, t.sub_type, t.name
LIMIT %s OFFSET %s
                """,
            ).format(base=base_sql),
            [*params, limit, offset],
        )
        items = await cur.fetchall()
    return items, total


async def upsert_tag_translation(
    conn: psycopg.AsyncConnection,
    tag_id: int,
    language: str,
    content: str,
) -> bool:
    """Create or update a tag translation row.

    Returns False when the tag does not exist.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT 1 FROM tag WHERE id = %s",
            (tag_id,),
        )
        if await cur.fetchone() is None:
            return False
        await cur.execute(
            """
INSERT INTO tag_translation (tag_id, language, content)
VALUES (%s, %s, %s)
ON CONFLICT (tag_id, language) DO UPDATE SET content = EXCLUDED.content
            """,
            (tag_id, language, content),
        )
        return True


async def update_tag_translation(
    conn: psycopg.AsyncConnection,
    tag_id: int,
    language: str,
    content: str,
) -> bool:
    """Update the content of an existing tag translation row."""
    async with conn.cursor() as cur:
        await cur.execute(
            """
UPDATE tag_translation
SET content = %s
WHERE tag_id = %s AND language = %s
            """,
            (content, tag_id, language),
        )
        return cur.rowcount > 0


async def delete_tag_translation(
    conn: psycopg.AsyncConnection,
    tag_id: int,
    language: str,
) -> bool:
    """Delete a tag translation row by its natural key."""
    async with conn.cursor() as cur:
        await cur.execute(
            """
DELETE FROM tag_translation
WHERE tag_id = %s AND language = %s
            """,
            (tag_id, language),
        )
        return cur.rowcount > 0


async def batch_upsert_tag_translations(
    conn: psycopg.AsyncConnection,
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    """Batch upsert translations by tag name.

    Each entry: {"tag_name", "language", "content"}. Every tag row sharing
    the same name (multiple types allowed) gets the translation.
    """
    stats: dict[str, Any] = {"updated": 0, "missing": []}
    names = [entry["tag_name"] for entry in entries]
    if not names:
        return stats
    async with conn.cursor(row_factory=rows.dict_row) as cur:
        await cur.execute(
            "SELECT id, type, name FROM tag WHERE name = ANY(%s)",
            (names,),
        )
        matched = await cur.fetchall()
    matched_by_name: dict[str, list[dict[str, Any]]] = {}
    for row in matched:
        matched_by_name.setdefault(row["name"], []).append(row)
    for entry in entries:
        tag_rows = matched_by_name.get(entry["tag_name"])
        if not tag_rows:
            stats["missing"].append(entry["tag_name"])
            continue
        async with conn.cursor() as cur:
            for tag_row in tag_rows:
                await cur.execute(
                    """
INSERT INTO tag_translation (tag_id, language, content)
VALUES (%s, %s, %s)
ON CONFLICT (tag_id, language) DO UPDATE SET content = EXCLUDED.content
                    """,
                    (tag_row["id"], entry["language"], entry["content"]),
                )
        stats["updated"] += len(tag_rows)
    return stats


async def search_tags(
    conn: psycopg.AsyncConnection,
    query: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Search the tag directory by name substring."""
    async with conn.cursor(row_factory=rows.dict_row) as cur:
        await cur.execute(
            ("SELECT id, name, type, sub_type FROM tag WHERE name ILIKE %s ORDER BY name LIMIT %s"),
            (f"%{query}%", limit),
        )
        return await cur.fetchall()


async def get_tag_by_id(
    conn: psycopg.AsyncConnection,
    tag_id: int,
) -> dict[str, Any] | None:
    """Fetch a single tag directory row by id."""
    async with conn.cursor(row_factory=rows.dict_row) as cur:
        await cur.execute(
            "SELECT id, name, type, sub_type FROM tag WHERE id = %s",
            (tag_id,),
        )
        return await cur.fetchone()


async def list_image_tag_assoc(
    conn: psycopg.AsyncConnection,
    query: str = "",
    offset: int = 0,
    limit: int = 10,
) -> tuple[list[dict[str, Any]], int]:
    """List image-tag associations, optionally filtered by filename or tag name."""
    where_clause = sql.SQL("")
    params: list[Any] = []
    if query:
        where_clause = sql.SQL("WHERE i.filename ILIKE %s OR t.name ILIKE %s")
        like = f"%{query}%"
        params = [like, like]
    list_sql = sql.SQL(
        """
SELECT
    a.image_id,
    i.filename AS image_filename,
    a.tag_id,
    t.name AS tag_name,
    a.type AS tag_type,
    a.score
FROM image_tag_assoc a
JOIN image i ON i.id = a.image_id
JOIN tag t ON t.id = a.tag_id
{where}
ORDER BY a.image_id DESC, a.tag_id
LIMIT %s OFFSET %s
        """,
    ).format(where=where_clause)
    count_sql = sql.SQL(
        """
SELECT count(*)
FROM image_tag_assoc a
JOIN image i ON i.id = a.image_id
JOIN tag t ON t.id = a.tag_id
{where}
        """,
    ).format(where=where_clause)
    async with conn.cursor(row_factory=rows.dict_row) as cur:
        await cur.execute(list_sql, [*params, limit, offset])
        items = await cur.fetchall()
        await cur.execute(count_sql, params)
        row = await cur.fetchone()
        if row is None:
            raise RuntimeError("count 查询失败")
        total = row["count"]
    return items, total


async def add_image_tag_assoc(
    conn: psycopg.AsyncConnection,
    image_id: int,
    tag_id: int,
    score: float,
) -> tuple[str, int]:
    """Add an existing tag to an image.

    Returns ("created", tag_id) or ("duplicate", tag_id); when the image or
    the tag does not exist, returns ("image_missing", tag_id) or
    ("tag_missing", tag_id).
    """
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT 1 FROM image WHERE id = %s",
            (image_id,),
        )
        if await cur.fetchone() is None:
            return "image_missing", tag_id
        await cur.execute(
            "SELECT 1 FROM tag WHERE id = %s",
            (tag_id,),
        )
        if await cur.fetchone() is None:
            return "tag_missing", tag_id
        await cur.execute(
            """
INSERT INTO image_tag_assoc (image_id, tag_id, type, score)
SELECT %s, %s, type, %s FROM tag WHERE id = %s
ON CONFLICT (image_id, tag_id) DO NOTHING
            """,
            (image_id, tag_id, score, tag_id),
        )
        return ("created" if cur.rowcount > 0 else "duplicate"), tag_id


async def delete_image_tag_assoc(
    conn: psycopg.AsyncConnection,
    image_id: int,
    tag_id: int,
) -> bool:
    """Delete an image-tag association row."""
    async with conn.cursor() as cur:
        await cur.execute(
            "DELETE FROM image_tag_assoc WHERE image_id = %s AND tag_id = %s",
            (image_id, tag_id),
        )
        return cur.rowcount > 0
