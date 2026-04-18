"""
Prism v2 — API v1 Router Aggregator

Registers all v1 sub-routers and mounts them under /api/v1.

Routers:
  providers  — Provider CRUD + presets + test (DOC-02 Task 2.3)
  harness    — GET /harness/config readonly (DOC-03 Task 3.6)
"""
from fastapi import APIRouter

from app.api.v1.providers import router as providers_router
from app.api.v1 import harness

# Master v1 router
api_v1_router = APIRouter(prefix="/api/v1")

# Register sub-routers
api_v1_router.include_router(providers_router)
api_v1_router.include_router(harness.router)
