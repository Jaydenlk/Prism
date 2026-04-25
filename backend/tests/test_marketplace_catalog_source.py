"""Tests for MarketplaceCatalogSource (fix#3+ Skills search 数据源重构).

Mock db_session_factory + fake MarketplaceRegistry rows;不依赖真 DB。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import pytest

from executor.plugins.skills_registry import MarketplaceCatalogSource


@dataclass
class _FakeMpRow:
    """模拟 MarketplaceRegistry ORM row(避免 import backend models)。"""
    id: str
    name: str
    catalog_json: dict[str, Any] | None


def _make_session_factory(rows: list[_FakeMpRow]):
    """构造 db_session_factory:每次调用返回新 mock session。"""
    def factory():
        sess = MagicMock()
        sess.query.return_value.all.return_value = rows
        sess.close = MagicMock()
        return sess
    return factory


@pytest.mark.asyncio
async def test_empty_marketplace_registry_returns_empty():
    src = MarketplaceCatalogSource(db_session_factory=_make_session_factory([]))
    assert await src.search("") == []
    assert await src.search("anything") == []


@pytest.mark.asyncio
async def test_single_marketplace_one_plugin_query_empty_returns_one():
    rows = [_FakeMpRow(
        id="m1", name="test-mp",
        catalog_json={"name": "test-mp", "owner": {"name": "tester"},
            "plugins": [{"name": "p1", "description": "d1", "version": "1.0"}]},
    )]
    src = MarketplaceCatalogSource(db_session_factory=_make_session_factory(rows))
    res = await src.search("")
    assert len(res) == 1
    assert res[0].name == "p1"
    assert res[0].source == "marketplace"
    assert res[0].source_url == "marketplace://test-mp/p1"
    assert res[0].version == "1.0"


@pytest.mark.asyncio
async def test_query_matches_name_substring():
    rows = [_FakeMpRow("m1", "mp", {"plugins": [
        {"name": "github-tool", "description": ""},
        {"name": "linear-tool", "description": ""},
    ]})]
    src = MarketplaceCatalogSource(db_session_factory=_make_session_factory(rows))
    res = await src.search("github")
    assert len(res) == 1
    assert res[0].name == "github-tool"


@pytest.mark.asyncio
async def test_query_matches_description():
    rows = [_FakeMpRow("m1", "mp", {"plugins": [
        {"name": "p1", "description": "Manage GitHub repositories"},
        {"name": "p2", "description": "Manage Linear projects"},
    ]})]
    src = MarketplaceCatalogSource(db_session_factory=_make_session_factory(rows))
    res = await src.search("github")
    assert len(res) == 1
    assert res[0].name == "p1"


@pytest.mark.asyncio
async def test_query_matches_keywords_or_tags():
    rows = [_FakeMpRow("m1", "mp", {"plugins": [
        {"name": "p1", "description": "", "keywords": ["dev", "git"]},
        {"name": "p2", "description": "", "tags": ["data", "ml"]},
    ]})]
    src = MarketplaceCatalogSource(db_session_factory=_make_session_factory(rows))
    res = await src.search("git")
    # p1 matched by keywords, p2 not
    assert len(res) == 1
    assert res[0].name == "p1"
    res2 = await src.search("ml")
    assert len(res2) == 1
    assert res2[0].name == "p2"


@pytest.mark.asyncio
async def test_query_no_match_returns_empty():
    rows = [_FakeMpRow("m1", "mp", {"plugins": [
        {"name": "alpha", "description": "Something"},
    ]})]
    src = MarketplaceCatalogSource(db_session_factory=_make_session_factory(rows))
    res = await src.search("nonexistent-zzz")
    assert res == []


@pytest.mark.asyncio
async def test_multiple_marketplaces_query_empty_merges_all():
    rows = [
        _FakeMpRow("m1", "mp1", {"plugins": [{"name": "a"}, {"name": "b"}]}),
        _FakeMpRow("m2", "mp2", {"plugins": [{"name": "c"}]}),
    ]
    src = MarketplaceCatalogSource(db_session_factory=_make_session_factory(rows))
    res = await src.search("")
    names = sorted(p.name for p in res)
    assert names == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_plugin_entry_missing_name_skipped_no_crash():
    rows = [_FakeMpRow("m1", "mp", {"plugins": [
        {"name": "good", "description": ""},
        {"description": "no name field"},  # 缺 name → skip
        "not-a-dict",  # 非 dict → skip
        {"name": "", "description": "empty name"},  # 空 name → skip
    ]})]
    src = MarketplaceCatalogSource(db_session_factory=_make_session_factory(rows))
    res = await src.search("")
    assert len(res) == 1
    assert res[0].name == "good"


@pytest.mark.asyncio
async def test_author_object_or_string_normalized():
    rows = [_FakeMpRow("m1", "mp", {"plugins": [
        {"name": "p1", "author": {"name": "Acme"}},
        {"name": "p2", "author": "PlainStr"},
        {"name": "p3"},
    ]})]
    src = MarketplaceCatalogSource(db_session_factory=_make_session_factory(rows))
    res = await src.search("")
    by_name = {p.name: p for p in res}
    assert by_name["p1"].author == "Acme"
    assert by_name["p2"].author == "PlainStr"
    assert by_name["p3"].author is None
