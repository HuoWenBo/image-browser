"""Language resolution dependency for the image API.

Display-language rules:
- explicit ``lang`` query param wins when it is a supported language;
- otherwise the first supported language from ``Accept-Language`` is used;
- anything else falls back to the default (en).
"""

from typing import Annotated

from fastapi import Depends, Header, Query

SUPPORTED_LANGUAGES = ("en", "zh")
DEFAULT_LANGUAGE = "en"


def resolve_language(
    accept_language: str | None = Header(None),
    lang: str | None = Query(None),
) -> str:
    """Resolve the display language for tag translations."""
    if lang and lang.lower() in SUPPORTED_LANGUAGES:
        return lang.lower()
    if accept_language:
        for part in accept_language.split(","):
            code = part.split(";")[0].strip().lower()
            if code.startswith("zh"):
                return "zh"
            if code.startswith("en"):
                return "en"
    return DEFAULT_LANGUAGE


Language = Annotated[str, Depends(resolve_language)]
