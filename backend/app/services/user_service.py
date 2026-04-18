"""
Prism v2 — User Query Service (DOC-06 Task 6.1)

Thin service layer over the users table.  Authentication logic lives in
auth_service.py; this module only handles lookups and field updates.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.user import User


class UserService:
    """Low-level user record operations."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_by_id(self, user_id: str) -> User | None:
        """Return the User row with *user_id* or None if not found."""
        return self._db.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        """Return the User row with matching *email* (case-sensitive) or None."""
        return self._db.query(User).filter(User.email == email).first()

    def get_by_username(self, username: str) -> User | None:
        """Return the User row with matching *username* or None."""
        return self._db.query(User).filter(User.username == username).first()

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def update(self, user_id: str, **kwargs: object) -> User:
        """Apply *kwargs* as field updates to the user row.

        Only fields that exist on the User model are applied; unknown keys
        are silently ignored to avoid attribute errors during partial updates.

        Returns the updated User row.

        Raises:
            ValueError: If *user_id* is not found.
        """
        user = self.get_by_id(user_id)
        if user is None:
            raise ValueError(f"User {user_id!r} not found")
        for field, value in kwargs.items():
            if hasattr(user, field):
                setattr(user, field, value)
        self._db.flush()
        return user
