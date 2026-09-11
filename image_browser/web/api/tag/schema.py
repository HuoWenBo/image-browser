from pydantic import BaseModel

from image_browser.db.models.image import TagSubType, TagType


class TagSearchItem(BaseModel):
    """A tag directory entry for the add-tag suggestion dropdown."""

    id: int
    name: str
    type: TagType
    sub_type: TagSubType | None = None
