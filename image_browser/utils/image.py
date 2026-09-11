import hashlib
import os
import re
from io import BytesIO
from os import PathLike
from pathlib import Path
from typing import IO, Any, Self, TypedDict, cast

import numpy as np
import scipy
from imgutils import tagging
from pandas import DataFrame
from PIL import Image

from image_browser.settings import settings

SERIES_PATTERN = re.compile(r"(?<=\()([^)]+)(?=\))")
CLEAR_PATTERN = re.compile(r"\(.*\)")


def get_all_tags(model_name: str | None = None) -> tuple[DataFrame, dict[str, list[str]]]:
    """Load the tag name index used to split character series from tags."""
    # noinspection PyProtectedMember
    from imgutils.tagging.pixai import _open_tags

    df_tags, d_ips = _open_tags(model_name=model_name or settings.tag_model_name)

    return df_tags, d_ips


class ImageMetadata(TypedDict):
    """Image Metadata Class."""

    width: int
    height: int
    format: str
    filesize: int
    signature: bytes
    fingerprint: list[float]


class ImageInfo(ImageMetadata):
    """Image Info Class."""

    tags: dict[str, float]
    character: dict[str, float]
    series: dict[str, float]


class ImageProcessor:
    """Image Processor Class."""

    CHUNK_SIZE = 1024 * 64  # 64KB 分块

    def __init__(
        self,
        image: Image.Image,
        filesize: int,
        signature: bytes,
    ) -> None:
        """Init Image Processor."""
        self._image = image
        self._filesize = filesize
        self._signature = signature

    @property
    def image(self) -> Image.Image:
        """Return Image."""
        return self._image

    @property
    def signature(self) -> bytes:
        """Return Image signature."""
        return self._signature

    @property
    def filesize(self) -> int:
        """Return Image file size."""
        return self._filesize

    @classmethod
    def _stream_read_meta(
        cls,
        fp: str | bytes | PathLike[str] | PathLike[bytes] | IO[bytes],
    ) -> tuple[BytesIO, int, bytes]:
        """Stream-read image bytes, computing size and sha256 into BytesIO.

        No full bytes copy is kept besides the BytesIO buffer.
        Returns (BytesIO, filesize, sha256_hex).
        """
        if isinstance(fp, str):
            fp = Path(fp)

        bio = BytesIO()
        sha_obj = hashlib.sha256()
        total_size = 0

        if isinstance(fp, PathLike):
            with Path(cast(str, os.fspath(fp))).open("rb") as f:
                while chunk := f.read(cls.CHUNK_SIZE):
                    sha_obj.update(chunk)
                    bio.write(chunk)
                    total_size += len(chunk)

        elif isinstance(fp, bytes):
            sha_obj.update(fp)
            bio.write(fp)
            total_size = len(fp)

        elif getattr(fp, "read", None) is not None:
            while chunk := fp.read(cls.CHUNK_SIZE):
                sha_obj.update(chunk)
                bio.write(chunk)
                total_size += len(chunk)
            fp.seek(0)
        else:
            raise ValueError(f"不支持的输入类型：{type(fp)}")

        bio.seek(0)  # BytesIO指针重置到开头，给Image.open读取
        return bio, total_size, sha_obj.digest()

    @classmethod
    def open_image(
        cls,
        fp: str | bytes | PathLike[str] | PathLike[bytes] | IO[bytes],
    ) -> Self:
        """Open Image."""
        bio, filesize, signature = cls._stream_read_meta(fp)
        pil_img = Image.open(bio)

        return cls(pil_img, filesize, signature)

    def get_metadata(self) -> ImageMetadata:
        """Return Image Metadata."""
        return {
            "width": self._image.width,
            "height": self._image.height,
            "format": (self._image.format if self._image.format else "UNKNOWN"),
            "filesize": self._filesize,
            "signature": self._signature,
            "fingerprint": self.compute_dct_vector(),
        }

    def compute_dct_vector(
        self,
        hash_size: int = 16,
        normalize: bool = True,
    ) -> list[float]:
        """Compute dct vector."""
        img_size = hash_size * 4
        img = self._image.convert("L").resize(
            (img_size, img_size),
            Image.Resampling.LANCZOS,
        )
        pixels = np.asarray(img).astype(np.float32)

        dct = scipy.fftpack.dct(scipy.fftpack.dct(pixels, axis=0), axis=1)
        dct_low = dct[:hash_size, :hash_size].flatten()
        # 去除 DC 分量（索引0）
        vec = dct_low[1:]  # 长度为 hash_size^2 - 1

        if normalize:
            norm = np.linalg.norm(vec)
            if norm > 1e-8:
                vec = vec / norm

        return vec.tolist()

    def extract_tags(
        self,
        model_name: str | None = None,
        thresholds: float | dict[Any, float] | None = None,
    ) -> tuple[dict[Any, float], dict[Any, float], dict[Any, float]]:
        """Extract tags."""
        generals, characters = tagging.get_pixai_tags(
            self._image,
            model_name or settings.tag_model_name,
            thresholds,
        )
        _, d_ips = get_all_tags()

        series = {}

        for key, value in characters.items():
            if key in d_ips:
                for name in d_ips[key]:
                    series[name] = value

        return generals, characters, series

    def build_info(
        self,
    ) -> ImageInfo:
        """Build Image Info."""
        tags, character, series = self.extract_tags()
        return ImageInfo(
            tags=tags,
            character=character,
            series=series,
            **self.get_metadata(),
        )
