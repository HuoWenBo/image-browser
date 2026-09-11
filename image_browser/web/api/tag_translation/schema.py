from pydantic import BaseModel, Field

from image_browser.db.models.image import TagSubType, TagType


class TagTranslationCreate(BaseModel):
    """Payload to create or update one tag translation."""

    tag_id: int
    language: str = Field(min_length=1, max_length=16)
    content: str = Field(min_length=1, max_length=512)


class TagTranslationUpdate(BaseModel):
    """Payload to update the content of a tag translation."""

    content: str = Field(min_length=1, max_length=512)


class TagTranslationItem(BaseModel):
    """A tag translation row joined with its tag name."""

    tag_id: int
    tag_name: str
    type: TagType
    sub_type: TagSubType | None = None
    language: str
    content: str


class TagTranslationListResponse(BaseModel):
    """Paginated tag translation list."""

    items: list[TagTranslationItem]
    total: int
    page: int
    per_page: int
    total_pages: int


class MissingTranslationItem(BaseModel):
    """A tag directory entry without any translation."""

    tag_id: int
    tag_name: str
    type: TagType
    sub_type: TagSubType | None = None


class MissingTranslationListResponse(BaseModel):
    """Paginated list of tags missing translations."""

    items: list[MissingTranslationItem]
    total: int
    page: int
    per_page: int
    total_pages: int


class BatchTranslationEntry(BaseModel):
    """One line of a batch import: tag name + content."""

    tag_name: str = Field(min_length=1)
    language: str = Field(min_length=1, max_length=16)
    content: str = Field(min_length=1, max_length=512)


class BatchImportRequest(BaseModel):
    """Batch import payload."""

    entries: list[BatchTranslationEntry] = Field(min_length=1, max_length=1000)


class BatchImportResult(BaseModel):
    """Batch import outcome."""

    updated: int
    missing: list[str]
