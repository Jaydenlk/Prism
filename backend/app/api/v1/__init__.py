"""
Prism v2 — API v1 Router Aggregator

Registers all v1 sub-routers and mounts them under /api/v1.

Routers:
  auth       — JWT login / register / refresh / logout / me / sse-ticket (DOC-06 Task 6.1)
  providers  — Provider CRUD + presets + test (DOC-02 Task 2.3)
  harness    — GET /harness/config readonly (DOC-03 Task 3.6)
  skills     — Skills Market search/install/uninstall (DOC-05 Task 5.6)
  plugins    — Plugin load/validate/export-cc (DOC-05 Task 5.7)
"""
from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.providers import router as providers_router
from app.api.v1 import harness
from app.api.v1.skills import router as skills_router
from app.api.v1.plugins import router as plugins_router

# Master v1 router
api_v1_router = APIRouter(prefix="/api/v1")

# Register sub-routers
api_v1_router.include_router(auth_router)
api_v1_router.include_router(providers_router)
api_v1_router.include_router(harness.router)
api_v1_router.include_router(skills_router)
api_v1_router.include_router(plugins_router)
