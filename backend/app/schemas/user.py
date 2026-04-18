"""
Prism v2 — User Management Schemas (DOC-06 Task 6.2)

Request / response models for admin user-management endpoints.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class UserListResponse(BaseModel):
    """Returned by GET /admin/users and PATCH /admin/users/{id}."""

    id: str
    email: str
    username: str
    role: str
    last_login_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class UpdateUserRoleRequest(BaseModel):
    """PATCH /admin/users/{id} — change the user's role."""

    role: Literal["admin", "user"]
