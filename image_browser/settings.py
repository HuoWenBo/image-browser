import enum
from pathlib import Path
from tempfile import gettempdir

from pydantic_settings import BaseSettings, SettingsConfigDict
from yarl import URL

TEMP_DIR = Path(gettempdir())
# Project root directory (image_browser/settings.py -> project root).
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class LogLevel(enum.StrEnum):
    """Possible log levels."""

    NOTSET = "NOTSET"
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    FATAL = "FATAL"


class Settings(BaseSettings):
    """
    Application settings.

    These parameters can be configured
    with environment variables.
    """

    host: str = "127.0.0.1"
    port: int = 8000
    # quantity of workers for uvicorn
    workers_count: int = 1
    # Enable uvicorn reloading
    reload: bool = False

    # Current environment
    environment: str = "dev"

    log_level: LogLevel = LogLevel.INFO
    # Variables for the database
    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "image_browser"
    db_pass: str = "image_browser"  # noqa: S105
    db_base: str = "admin"
    db_echo: bool = False
    # Database schema used by the application (all tables live here).
    db_schema: str = "public"

    # Hybrid image search
    search_fingerprint_threshold: float = 0.85
    search_fingerprint_weight: float = 0.5
    search_tag_weight: float = 0.5
    # Minimum model tag confidence kept for the hybrid search.
    search_tag_score_threshold: float = 0.35
    # Per-tag-type weights (JSON object) used by the hybrid search;
    # only the listed types participate in matching.
    search_tag_type_weights: str = '{"CHARACTER_NAME": 1.0, "COPYRIGHT": 0.3}'
    # Fulltext search weights, ordered [character, series, tag].
    search_fulltext_weights: list[int] = [10, 3, 1]
    search_fulltext_with_tags_weights: list[int] = [5, 3, 1]
    # Local tagging model name.
    tag_model_name: str = "v0.9"

    # Image storage directory (absolute, or relative to the project root).
    images_dir: str = "images"

    # Image DCT
    # image_dct_size: int =

    @property
    def images_dir_path(self) -> Path:
        """
        Absolute image storage directory.

        :return: absolute Path to the image storage directory.
        """
        path = Path(self.images_dir)
        return path if path.is_absolute() else PROJECT_ROOT / path

    @property
    def db_url(self) -> URL:
        """
        Assemble database URL from settings.

        :return: database URL.
        """
        return URL.build(
            scheme="postgresql",
            host=self.db_host,
            port=self.db_port,
            user=self.db_user,
            password=self.db_pass,
            path=f"/{self.db_base}",
        )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="IMAGE_BROWSER_",
        env_file_encoding="utf-8",
    )


settings = Settings()
