from datetime import datetime
from enum import StrEnum

from pgvector import Vector
from pydantic import BaseModel, Field, field_serializer, field_validator


class TagType(StrEnum):
    """Tag Type."""

    COPYRIGHT = "COPYRIGHT"
    CHARACTER_NAME = "CHARACTER_NAME"
    GENERAL = "GENERAL"


class TagSubType(StrEnum):
    """Tag Sub Type."""

    CHARACTER = "CHARACTER"
    FACE_FEATURES = "FACE_FEATURES"
    LIGHT_SHADOW = "LIGHT_SHADOW"
    ACTION = "ACTION"
    ANIMAL = "ANIMAL"
    HAIRSTYLE = "HAIRSTYLE"
    SCENE = "SCENE"
    POSE = "POSE"
    TEXT = "TEXT"
    CLOTHING = "CLOTHING"
    COMPOSITION = "COMPOSITION"
    ITEM = "ITEM"
    ART_STYLE = "ART_STYLE"
    BACKGROUND = "BACKGROUND"
    EXPRESSION = "EXPRESSION"
    EYE_SIGHT = "EYE_SIGHT"
    QUALITY = "QUALITY"
    BODY = "BODY"
    OTHER = "OTHER"


class Image(BaseModel):
    """
    Image Model.

    Storage image metadata
    """

    id: int | None = None

    width: int
    height: int
    format: str
    filesize: int
    signature: bytes
    fingerprint: list[float]
    filename: str
    filepath: str

    created_at: datetime | None = None
    modified_at: datetime | None = None

    @field_validator("fingerprint", mode="before")
    @classmethod
    def parse_fingerprint(cls, v: list[float] | Vector | bytes) -> list[float]:
        """Parse Finger Print Image."""
        if isinstance(v, bytes):
            v = Vector.from_binary(v)
            return v.to_list()
        if isinstance(v, Vector):
            return v.to_list()

        return v

    @field_serializer("signature")
    def serialize_bytes(self, v: bytes) -> str:
        """Serialize Finger Print Image."""
        return v.hex()


class ImageTag(BaseModel):
    """
    Image Tag Model.

    Storage image tag
    """

    id: int | None = None
    image_id: int

    language: str
    characters: list[str] = Field(default_factory=list)
    series: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    created_at: datetime | None = None
    modified_at: datetime | None = None


class Tag(BaseModel):
    """Tag Model."""

    id: int | None = None
    name: str
    type: TagType = TagType.GENERAL
    sub_type: TagSubType | None = None


class TagTarn(BaseModel):
    """
    Tag Tarn Model.

    Storage tag translation content
    """

    tag_id: int
    type: TagType = TagType.GENERAL
    language: str

    content: str
