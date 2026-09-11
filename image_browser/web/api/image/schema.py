from datetime import datetime

from pydantic import BaseModel, Field

from image_browser.db.models.image import TagType


class ImageListItem(BaseModel):
    """Image list item with current-language tags."""

    id: int
    width: int
    height: int
    format: str
    filesize: int
    filename: str
    filepath: str
    created_at: datetime | None = None
    modified_at: datetime | None = None
    tags: list[str] = Field(default_factory=list)
    characters: list[str] = Field(default_factory=list)
    series: list[str] = Field(default_factory=list)


class ImageListResponse(BaseModel):
    """Paginated image list response."""

    items: list[ImageListItem]
    total: int
    page: int
    per_page: int
    total_pages: int


class ImageTagItem(BaseModel):
    """Raw tag item with confidence score and optional translation."""

    id: int
    type: TagType
    name: str
    score: float
    content: str | None = None


class ImageCreate(BaseModel):
    """Create or replace an image record (signature is a hex string)."""

    width: int
    height: int
    format: str
    filesize: int
    signature: str
    fingerprint: list[float] = Field(default_factory=list, min_length=1)
    filename: str
    filepath: str


class UploadResult(BaseModel):
    """Upload result of a single image file."""

    filename: str
    status: str
    message: str = ""
    image_id: int | None = None


class ImageDetail(BaseModel):
    """Image detail response with translated tags and raw scores."""

    id: int
    width: int
    height: int
    format: str
    filesize: int
    signature: str
    fingerprint: list[float]
    filename: str
    filepath: str
    created_at: datetime | None = None
    modified_at: datetime | None = None
    tags: list[str] = Field(default_factory=list)
    characters: list[str] = Field(default_factory=list)
    series: list[str] = Field(default_factory=list)
    scores: dict[str, list[ImageTagItem]] = Field(default_factory=dict)
