# ruff: noqa: S608, T201 - init script: SQL fragments and prints are intended
"""Initialize the database schema and seed tag / tag_translation data.

Creates the extensions, enums, sequences, tables, indexes and foreign keys
used by the application in the configured schema (``IMAGE_BROWSER_DB_SCHEMA``,
default ``public``), then imports ``tag`` and ``tag_translation`` from the
exported data files in ``data/`` when the target tables are empty.

Usage:
    uv run python init.py
"""

import argparse
import asyncio
import json
import pathlib
import selectors

import psycopg
from psycopg import sql

from image_browser.settings import settings

DATA_DIR = pathlib.Path(__file__).resolve().parent / "data"

TAG_TYPE_VALUES = ("COPYRIGHT", "CHARACTER_NAME", "GENERAL")

TAG_SUB_TYPE_VALUES = (
    "CHARACTER",
    "FACE_FEATURES",
    "LIGHT_SHADOW",
    "ACTION",
    "ANIMAL",
    "HAIRSTYLE",
    "SCENE",
    "POSE",
    "TEXT",
    "CLOTHING",
    "COMPOSITION",
    "ITEM",
    "ART_STYLE",
    "BACKGROUND",
    "EXPRESSION",
    "EYE_SIGHT",
    "QUALITY",
    "BODY",
    "OTHER",
)


def _enum_block(type_name: str, values: tuple[str, ...]) -> str:
    """Build a DO block that creates an enum type only if it is missing."""
    labels = ", ".join(f"'{v}'" for v in values)
    return f"""
DO $do$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE t.typname = '{type_name}'
          AND n.nspname = current_schema()
    ) THEN
        CREATE TYPE {type_name} AS ENUM ({labels});
    END IF;
END
$do$;
"""


SCHEMA_STATEMENTS: list[str] = [
    _enum_block("tag_type", TAG_TYPE_VALUES),
    _enum_block("tag_sub_type", TAG_SUB_TYPE_VALUES),
    # Sequences (kept explicit so the id defaults match the legacy schema).
    "CREATE SEQUENCE IF NOT EXISTS image_id_seq",
    "CREATE SEQUENCE IF NOT EXISTS tag_id_seq",
    # Tables.
    """
CREATE TABLE IF NOT EXISTS image (
    id integer NOT NULL DEFAULT nextval('image_id_seq'::regclass),
    width integer NOT NULL,
    height integer NOT NULL,
    format character varying NOT NULL,
    filesize bigint NOT NULL,
    signature bytea NOT NULL,
    fingerprint vector(255),
    filename text NOT NULL,
    filepath text NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    modified_at timestamp with time zone DEFAULT now()
)
""",
    """
CREATE TABLE IF NOT EXISTS tag (
    id integer NOT NULL DEFAULT nextval('tag_id_seq'::regclass),
    type tag_type NOT NULL,
    sub_type tag_sub_type,
    name text NOT NULL
)
""",
    """
CREATE TABLE IF NOT EXISTS tag_translation (
    tag_id integer NOT NULL,
    language character varying NOT NULL,
    content text NOT NULL
)
""",
    """
CREATE TABLE IF NOT EXISTS image_tag_assoc (
    image_id integer NOT NULL,
    tag_id integer NOT NULL,
    type tag_type NOT NULL,
    score real NOT NULL
)
""",
    """
CREATE TABLE IF NOT EXISTS image_tag (
    image_id integer NOT NULL,
    language character varying NOT NULL,
    characters text[] DEFAULT '{}'::text[],
    series text[] DEFAULT '{}'::text[],
    tags text[] DEFAULT '{}'::text[],
    created_at timestamp with time zone DEFAULT now(),
    modified_at timestamp with time zone DEFAULT now()
)
""",
    """
CREATE TABLE IF NOT EXISTS series_character (
    series_id integer NOT NULL,
    character_id integer NOT NULL
)
""",
    # Primary keys, unique constraints and search indexes.
    "CREATE UNIQUE INDEX IF NOT EXISTS image_pkey ON image (id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS image_signature_key ON image (signature)",
    "CREATE INDEX IF NOT EXISTS idx_image_signature ON image (signature)",
    ("CREATE INDEX IF NOT EXISTS idx_image_fingerprint_hnsw ON image USING hnsw (fingerprint vector_cosine_ops)"),
    "CREATE UNIQUE INDEX IF NOT EXISTS tag_pkey ON tag (id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS tag_type_name_key ON tag (type, name)",
    ("CREATE UNIQUE INDEX IF NOT EXISTS tag_translation_pkey ON tag_translation (tag_id, language)"),
    ("CREATE UNIQUE INDEX IF NOT EXISTS image_tag_assoc_pkey ON image_tag_assoc (image_id, tag_id)"),
    ("CREATE INDEX IF NOT EXISTS idx_image_tag_assoc_tag_id ON image_tag_assoc (tag_id)"),
    ("CREATE UNIQUE INDEX IF NOT EXISTS image_tag_pkey ON image_tag (image_id, language)"),
    ("CREATE INDEX IF NOT EXISTS idx_image_tag_characters ON image_tag USING pgroonga (characters)"),
    ("CREATE INDEX IF NOT EXISTS idx_image_tag_series ON image_tag USING pgroonga (series)"),
    ("CREATE INDEX IF NOT EXISTS idx_image_tag_tags ON image_tag USING pgroonga (tags)"),
    ("CREATE UNIQUE INDEX IF NOT EXISTS series_character_pkey ON series_character (series_id, character_id)"),
    # Foreign keys (DO blocks keep the script idempotent).
    """
DO $do$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'image_tag_image_id_fkey'
          AND connamespace = current_schema()::regnamespace
    ) THEN
        ALTER TABLE image_tag
            ADD CONSTRAINT image_tag_image_id_fkey
            FOREIGN KEY (image_id) REFERENCES image (id) ON DELETE CASCADE;
    END IF;
END
$do$;
""",
    """
DO $do$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'image_tag_assoc_image_id_fkey'
          AND connamespace = current_schema()::regnamespace
    ) THEN
        ALTER TABLE image_tag_assoc
            ADD CONSTRAINT image_tag_assoc_image_id_fkey
            FOREIGN KEY (image_id) REFERENCES image (id) ON DELETE CASCADE;
    END IF;
END
$do$;
""",
    """
DO $do$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'image_tag_assoc_tag_id_fkey'
          AND connamespace = current_schema()::regnamespace
    ) THEN
        ALTER TABLE image_tag_assoc
            ADD CONSTRAINT image_tag_assoc_tag_id_fkey
            FOREIGN KEY (tag_id) REFERENCES tag (id) ON DELETE CASCADE;
    END IF;
END
$do$;
""",
    """
DO $do$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'series_character_series_id_fkey'
          AND connamespace = current_schema()::regnamespace
    ) THEN
        ALTER TABLE series_character
            ADD CONSTRAINT series_character_series_id_fkey
            FOREIGN KEY (series_id) REFERENCES tag (id) ON DELETE CASCADE;
    END IF;
END
$do$;
""",
    """
DO $do$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'series_character_character_id_fkey'
          AND connamespace = current_schema()::regnamespace
    ) THEN
        ALTER TABLE series_character
            ADD CONSTRAINT series_character_character_id_fkey
            FOREIGN KEY (character_id) REFERENCES tag (id) ON DELETE CASCADE;
    END IF;
END
$do$;
""",
    """
DO $do$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'tag_translation_tag_id_fkey'
          AND connamespace = current_schema()::regnamespace
    ) THEN
        ALTER TABLE tag_translation
            ADD CONSTRAINT tag_translation_tag_id_fkey
            FOREIGN KEY (tag_id) REFERENCES tag (id) ON DELETE CASCADE;
    END IF;
END
$do$;
""",
]

# Seed data files: table name, file name, column order in the JSON records.
SEED_TABLES: list[tuple[str, str, list[str]]] = [
    ("tag", "tag.json", ["id", "type", "sub_type", "name"]),
    (
        "tag_translation",
        "tag_translation.json",
        ["tag_id", "language", "content"],
    ),
]


async def _create_schema(conn: psycopg.AsyncConnection, schema: str) -> None:
    """Run the DDL statements against the given schema."""
    if schema != "public":
        await conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
    await conn.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))
    for statement in SCHEMA_STATEMENTS:
        await conn.execute(statement)


async def _import_seed_data(conn: psycopg.AsyncConnection) -> None:
    """Import tag / tag_translation from the exported data files."""
    for table, filename, columns in SEED_TABLES:
        row = await conn.execute(f"SELECT count(*) FROM {table}")
        if (await row.fetchone())[0] > 0:
            print(f"skip {table}: target not empty")
            continue
        path = DATA_DIR / filename
        if not path.exists():
            print(f"skip {table}: {filename} not found")
            continue
        records = json.loads(path.read_text(encoding="utf-8"))
        if not records:
            print(f"skip {table}: {filename} is empty")
            continue
        placeholders = ", ".join(["%s"] * len(columns))
        cols = ", ".join(columns)
        stmt = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
        async with conn.cursor() as cur:
            await cur.executemany(stmt, [tuple(record[c] for c in columns) for record in records])
        print(f"imported {table}: {len(records)} rows")

    # Keep id sequences in sync after importing explicit ids.
    for seq, table in (("image_id_seq", "image"), ("tag_id_seq", "tag")):
        await conn.execute(
            sql.SQL("SELECT setval({}, COALESCE((SELECT max(id) FROM {}), 1))").format(sql.Literal(seq), sql.Identifier(table))
        )


async def main(args: argparse.Namespace) -> None:
    """Run the initialization flow."""
    conn = await psycopg.AsyncConnection.connect(str(settings.db_url))
    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS pgroonga")
        await _create_schema(conn, args.schema)
        await _import_seed_data(conn)
        await conn.commit()
        print(f"init complete: schema={args.schema}")
    finally:
        await conn.close()


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--schema",
        default=settings.db_schema,
        help="target schema (default: from settings)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(
        main(parse_args()),
        loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
    )
