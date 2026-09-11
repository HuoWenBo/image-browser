from typing import Annotated

from fastapi import Depends
from pydantic import BaseModel, Field

CurPage = Annotated[int, Field(ge=1, description="页码")]
PerPage = Annotated[int, Field(ge=1, le=100, description="每页条数")]


class PaginatorParams(BaseModel):
    """Shared pagination parameters for RESTful list endpoints."""

    page: CurPage = 1
    per_page: PerPage = 12

    @property
    def limit(self) -> int:
        """Return per-page limit for SQL LIMIT clause."""
        return self.per_page

    @property
    def offset(self) -> int:
        """Return SQL OFFSET computed from page and per_page."""
        return (self.page - 1) * self.per_page


def get_paginator(
    page: CurPage = 1,
    per_page: PerPage = 12,
) -> PaginatorParams:
    """Build PaginatorParams from query parameters (FastAPI dependency)."""
    return PaginatorParams(page=page, per_page=per_page)


def calc_total_pages(total: int, per_page: int) -> int:
    """Calculate total page count without division by zero."""
    if per_page <= 0:
        return 1
    return (total + per_page - 1) // per_page


Paginator = Annotated[PaginatorParams, Depends(get_paginator)]
