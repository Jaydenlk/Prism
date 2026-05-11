from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

import structlog

from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.memory_service import MemoryService

logger = structlog.get_logger()

router = APIRouter(prefix="/memories", tags=["memories"])


class AddMemoryRequest(BaseModel):
    content: str


@router.get("", response_model=ApiResponse[list[dict]])
async def list_memories(
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[list[dict]]:
    svc = MemoryService()
    memories = await svc.list_memories(str(user.id))
    logger.info("memory.list", user_id=str(user.id), count=len(memories))
    return ApiResponse(data=memories)


@router.get("/search", response_model=ApiResponse[list[dict]])
async def search_memories(
    q: Annotated[str, Query(min_length=1)],
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    user: Annotated[User, Depends(get_current_user)] = None,
) -> ApiResponse[list[dict]]:
    svc = MemoryService()
    results = await svc.search_memories(str(user.id), query=q, limit=limit)
    logger.info("memory.search", user_id=str(user.id), query=q, count=len(results))
    return ApiResponse(data=results)


@router.post("", response_model=ApiResponse[dict], status_code=201)
async def add_memory(
    body: AddMemoryRequest,
    user: Annotated[User, Depends(get_current_user)] = None,
) -> ApiResponse[dict]:
    svc = MemoryService()
    result = await svc.add_memory(str(user.id), content=body.content)
    logger.info("memory.add", user_id=str(user.id))
    return ApiResponse(data=result)


@router.delete("/{memory_id}", status_code=204)
async def delete_memory(
    memory_id: str,
    user: Annotated[User, Depends(get_current_user)] = None,
) -> None:
    svc = MemoryService()
    await svc.delete_memory(memory_id)
    logger.info("memory.delete", user_id=str(user.id), memory_id=memory_id)
