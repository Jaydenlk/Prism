from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.message import Message
from app.models.session import Session as SessionModel
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.message import MessageResponse
from app.services.session_service import SessionService

import structlog
logger = structlog.get_logger()

router = APIRouter(tags=["shares"])


class ShareRequest(BaseModel):
    expires_in_days: int | None = 7


class ShareResponse(BaseModel):
    token: str
    url: str
    expires_at: datetime | None


class SharedSessionResponse(BaseModel):
    session: dict[str, Any]
    messages: list[MessageResponse]


@router.post(
    "/sessions/{session_id}/share",
    response_model=ApiResponse[ShareResponse],
    status_code=201,
)
def create_share(
    session_id: str,
    data: ShareRequest,
    user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> ApiResponse[ShareResponse]:
    svc = SessionService(db)
    session = svc.get_session(user.id, session_id)

    token = str(uuid.uuid4())
    expires_at: datetime | None = None
    if data.expires_in_days is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=data.expires_in_days)

    config = dict(session.config_snapshot or {})
    config["share"] = {
        "token": token,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "created_by": str(user.id),
    }
    session.config_snapshot = config
    flag_modified(session, "config_snapshot")
    session.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(session)

    logger.info("session.share.created", session_id=session_id, user_id=str(user.id), token=token)
    return ApiResponse(data=ShareResponse(token=token, url=f"/shared/{token}", expires_at=expires_at))


@router.get("/shared/{token}", response_model=ApiResponse[SharedSessionResponse])
def get_shared_session(
    token: str,
    db: Annotated[Session, Depends(get_db)] = None,
) -> ApiResponse[SharedSessionResponse]:
    session: SessionModel | None = (
        db.query(SessionModel)
        .filter(SessionModel.config_snapshot["share"]["token"].astext == token)
        .first()
    )
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared session not found")

    share = session.config_snapshot.get("share", {})
    expires_at_str: str | None = share.get("expires_at")
    if expires_at_str is not None:
        expires_at = datetime.fromisoformat(expires_at_str)
        if datetime.now(timezone.utc) > expires_at:
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="Share link has expired")

    messages = (
        db.query(Message)
        .filter(Message.session_id == session.id)
        .order_by(Message.sequence_no)
        .all()
    )
    message_items = [
        MessageResponse(
            id=m.id,
            run_id=m.run_id,
            role=m.role,
            content=m.content if isinstance(m.content, list) else [m.content],
            text_preview=m.text_preview,
            sequence_no=m.sequence_no,
            created_at=m.created_at,
        )
        for m in messages
    ]

    session_data = {
        "id": session.id,
        "title": session.title,
        "status": session.status,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
    }

    return ApiResponse(data=SharedSessionResponse(session=session_data, messages=message_items))


@router.delete("/sessions/{session_id}/share", status_code=204)
def revoke_share(
    session_id: str,
    user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> None:
    svc = SessionService(db)
    session = svc.get_session(user.id, session_id)

    config = dict(session.config_snapshot or {})
    if "share" not in config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active share for this session")

    del config["share"]
    session.config_snapshot = config
    flag_modified(session, "config_snapshot")
    session.updated_at = datetime.now(timezone.utc)
    db.commit()

    logger.info("session.share.revoked", session_id=session_id, user_id=str(user.id))
