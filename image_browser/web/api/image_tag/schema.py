from pydantic import BaseModel, Field

from image_browser.db.models.image import TagType


class ImageTagAssocCreate(BaseModel):
    """Payload to add an existing tag to an image."""

    image_id: int
    tag_id: int
    score: float = Field(ge=0, le=1, default=1.0)


class ImageTagAssocItem(BaseModel):
    """A single image-tag association row for the admin list."""

    image_id: int
    image_filename: str
    tag_id: int
    tag_name: str
    tag_type: TagType
    score: float


class ImageTagAssocListResponse(BaseModel):
    """Paginated list of image-tag associations."""

    items: list[ImageTagAssocItem]
    total: int
    page: int
    per_page: int
    total_pages: int
