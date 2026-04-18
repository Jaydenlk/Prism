"""
Prism v2 — Common Pydantic v2 Schemas (ADR-003)

All API responses are wrapped in ApiResponse[T] so clients always receive a
consistent envelope regardless of whether the call succeeded or failed.

Types exported
--------------
ErrorDetail      — {code, message} pair carried in error responses
ApiResponse[T]   — standard success envelope:  {data: T, error: null}
ErrorResponse    — standard failure envelope:   {data: null, error: ErrorDetail}
PagedResponse[T] — paginated list envelope:     {items, total, page, per_page}
"""
from __future__ import annotations

from typing import Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Error detail
# ---------------------------------------------------------------------------


class ErrorDetail(BaseModel):
    """Machine-readable error code + human-readable message."""

    code: str
    message: str


# ---------------------------------------------------------------------------
# Standard API envelope
# ---------------------------------------------------------------------------


class ApiResponse(BaseModel, Generic[T]):
    """
    Successful API response wrapper.

    ``error`` is always None on success; present only when ``data`` is None
    (i.e. ErrorResponse).  This mirrors CC's response contract.
    """

    data: T
    error: Optional[ErrorDetail] = None


class ErrorResponse(BaseModel):
    """
    Failed API response wrapper.

    ``data`` is always None; ``error`` carries the detail.
    """

    data: None = None
    error: ErrorDetail


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


class PagedResponse(BaseModel, Generic[T]):
    """Generic paginated list response."""

    items: list[T]
    total: int
    page: int
    per_page: int
    has_next: bool = False
    has_prev: bool = False

    @classmethod
    def from_query(
        cls,
        items: list[T],
        total: int,
        page: int,
        per_page: int,
    ) -> "PagedResponse[T]":
        return cls(
            items=items,
            total=total,
            page=page,
            per_page=per_page,
            has_next=(page * per_page) < total,
            has_prev=page > 1,
        )
