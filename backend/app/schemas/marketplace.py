"""
Prism v2 — Marketplace Pydantic schemas (DOC-SK R1, ADR-086)

Claude Code-compatible marketplace.json format
(https://code.claude.com/docs/en/plugin-marketplaces):

    {name, owner: {name, email?}, plugins: [...], metadata?}

`MarketplaceCatalog` models the fetched document shape; `MarketplaceResponse`
is the API envelope contents (DB row + catalog summary).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class MarketplaceCreate(BaseModel):
    """POST /marketplaces body."""

    url: HttpUrl = Field(description="URL to .claude-plugin/marketplace.json (or the bare marketplace.json)")
    name: str = Field(min_length=1, max_length=200, description="Display name shown in the UI")


class MarketplaceOwner(BaseModel):
    """`owner` field inside a CC marketplace.json."""

    name: str
    email: str | None = None


class MarketplacePluginEntry(BaseModel):
    """One entry inside `plugins: []` of a CC marketplace.json.

    Structure is permissive — we only validate the fields we actually consume
    (name + source). Other CC fields (version, author, keywords, category,
    strict, commands, agents, hooks, mcpServers, …) are preserved verbatim in
    `extra` so the UI can render them without a schema migration per new field.
    """

    name: str
    description: str | None = None
    version: str | None = None
    # source may be "./path" (string) OR an object like {source: "github", repo: "..."}
    source: str | dict[str, Any] | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class MarketplaceCatalog(BaseModel):
    """Parsed shape of the fetched `marketplace.json` document."""

    name: str
    owner: MarketplaceOwner | None = None
    plugins: list[MarketplacePluginEntry] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None


class MarketplaceResponse(BaseModel):
    """GET /marketplaces / POST /marketplaces response body."""

    id: str
    url: str
    name: str
    catalog_json: dict[str, Any] | None = None  # raw cached marketplace.json
    plugin_count: int = 0                        # derived from catalog_json.plugins
    last_fetched_at: str | None = None           # ISO 8601
    created_by: str
    created_at: str                              # ISO 8601
