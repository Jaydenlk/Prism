"""
Prism v2 — SSE Ticket Service (DOC-06 Task 6.1, ADR-051)

One-time SSE authentication ticket:
  - generate_ticket()      : SETEX sse_ticket:{uuid} 60s {user_id, session_id}
  - verify_and_consume()   : atomic GETDEL — prevents replay attacks

Redis key format: sse_ticket:{ticket_uuid}
TTL            : settings.SSE_TICKET_TTL_SECONDS (default 60 s)
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status


class SSETicketService:
    """Generate and atomically consume one-time SSE authentication tickets."""

    def __init__(self, redis_client, settings) -> None:
        """
        Args:
            redis_client: An async Redis client (redis.asyncio.Redis).
            settings:     The application Settings instance; must expose
                          ``SSE_TICKET_TTL_SECONDS`` (int, default 60).
        """
        self._redis = redis_client
        self._ttl: int = settings.SSE_TICKET_TTL_SECONDS

    # ------------------------------------------------------------------
    # Ticket generation
    # ------------------------------------------------------------------

    async def generate_ticket(self, user_id: str, session_id: str) -> dict:
        """Generate a one-time SSE ticket bound to *user_id* and *session_id*.

        The ticket is stored in Redis with SETEX so it auto-expires after
        ``SSE_TICKET_TTL_SECONDS`` seconds.

        Returns:
            ``{"ticket": "<uuid4>", "expires_at": "<ISO-8601 UTC>"}``
        """
        ticket = str(uuid.uuid4())
        key = f"sse_ticket:{ticket}"
        payload = json.dumps({"user_id": user_id, "session_id": session_id})

        await self._redis.setex(key, self._ttl, payload)

        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=self._ttl)
        ).isoformat()

        return {"ticket": ticket, "expires_at": expires_at}

    # ------------------------------------------------------------------
    # Ticket consumption (atomic GETDEL)
    # ------------------------------------------------------------------

    async def verify_and_consume(self, ticket: str, session_id: str) -> str:
        """Atomically consume *ticket* and return the bound ``user_id``.

        Uses GETDEL so the ticket is deleted in a single round-trip,
        making replay attacks impossible even under concurrent requests.

        Args:
            ticket:     The ticket UUID string from the client request.
            session_id: The session_id from the SSE connection URL — must
                        match the session_id stored in the ticket.

        Returns:
            ``user_id`` string bound to the ticket.

        Raises:
            HTTPException 401: ticket not found or already consumed or expired.
            HTTPException 403: ticket session_id does not match URL session_id.
        """
        key = f"sse_ticket:{ticket}"
        raw: bytes | None = await self._redis.getdel(key)

        if raw is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired SSE ticket",
            )

        data: dict = json.loads(raw)

        if data["session_id"] != session_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="SSE ticket session_id mismatch",
            )

        return data["user_id"]
