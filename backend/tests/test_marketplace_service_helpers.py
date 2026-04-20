"""Tests for MarketplaceService pure helpers (Session 4c).

Tests pure functions that don't require DB/Redis fixtures. End-to-end
install_plugin flow is covered by Playwright e2e (real DB + Redis + file I/O).
"""
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.marketplace_service import (
    _fetch_git,
    _looks_like_json_url,
    _parse_skill_frontmatter,
    _safe_name_from_url,
    _validate_marketplace_shape,
)


# ---------- _looks_like_json_url ----------


def test_looks_like_json_url_detects_direct_json():
    assert _looks_like_json_url("https://example.com/marketplace.json")
    assert _looks_like_json_url("http://example.com/path/to/mp.json")
    assert _looks_like_json_url("https://example.com/mp.json?ref=main")


def test_looks_like_json_url_rejects_git_shorthand():
    assert not _looks_like_json_url("anthropics/claude-plugins-official")
    assert not _looks_like_json_url("owner/repo")


def test_looks_like_json_url_rejects_git_https():
    assert not _looks_like_json_url("https://github.com/x/y.git")
    assert not _looks_like_json_url("https://github.com/x/y")
    assert not _looks_like_json_url("https://gitlab.com/team/plugin")


# ---------- _safe_name_from_url ----------


def test_safe_name_from_url_removes_protocol_and_git_suffix():
    assert _safe_name_from_url("https://github.com/owner/repo.git") == "github_com_owner_repo"
    assert _safe_name_from_url("git@github.com:x/y.git") == "github_com_x_y"


def test_safe_name_from_url_replaces_special_chars():
    assert _safe_name_from_url("https://example.com/a/b/c") == "example_com_a_b_c"


def test_safe_name_from_url_empty_fallback():
    assert _safe_name_from_url("") == "mp"


# ---------- _validate_marketplace_shape ----------


def test_validate_shape_accepts_minimal():
    parsed = {"name": "m", "owner": {"name": "n"}, "plugins": []}
    assert _validate_marketplace_shape(parsed)


def test_validate_shape_accepts_mixed_string_object_source():
    """Official anthropic marketplace.json mixes both forms (issue #1331)."""
    parsed = {
        "name": "m",
        "owner": {"name": "n"},
        "plugins": [
            {"name": "p1", "source": "./plugins/p1"},
            {"name": "p2", "source": {"source": "github", "repo": "x/y"}},
            {"name": "p3", "source": {"source": "git-subdir", "url": "a/b", "path": "p"}},
            {"name": "p4", "source": {"source": "npm", "package": "@x/y"}},
        ],
    }
    assert _validate_marketplace_shape(parsed)


def test_validate_shape_rejects_missing_name():
    assert not _validate_marketplace_shape({"owner": {"name": "x"}, "plugins": []})


def test_validate_shape_rejects_missing_owner_name():
    assert not _validate_marketplace_shape(
        {"name": "m", "owner": {}, "plugins": []}
    )


def test_validate_shape_rejects_plugins_not_list():
    assert not _validate_marketplace_shape(
        {"name": "m", "owner": {"name": "n"}, "plugins": "not-a-list"}
    )


def test_validate_shape_rejects_plugin_missing_name():
    assert not _validate_marketplace_shape(
        {
            "name": "m",
            "owner": {"name": "n"},
            "plugins": [{"source": "./x"}],
        }
    )


def test_validate_shape_rejects_non_dict():
    assert not _validate_marketplace_shape(None)
    assert not _validate_marketplace_shape("string")
    assert not _validate_marketplace_shape(123)


# ---------- _fetch_git (subprocess mocked) ----------


def test_fetch_git_normalizes_owner_repo_shorthand(tmp_path, monkeypatch):
    """owner/repo shorthand → https://github.com/owner/repo.git + clone."""
    import subprocess

    monkeypatch.setenv("PRISM_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        "app.services.marketplace_service._MARKETPLACE_CACHE",
        tmp_path / "marketplace_cache",
    )
    captured_cmd = []

    def fake_run(cmd, capture_output, text, timeout):
        captured_cmd.append(cmd)
        # simulate clone creating the target dir + marketplace.json
        target = Path(cmd[-1])
        target.mkdir(parents=True, exist_ok=True)
        mj_dir = target / ".claude-plugin"
        mj_dir.mkdir(parents=True, exist_ok=True)
        (mj_dir / "marketplace.json").write_text(
            '{"name":"m","owner":{"name":"n"},"plugins":[{"name":"p","source":"./foo"}]}'
        )
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with patch("subprocess.run", side_effect=fake_run):
        catalog, ts, local = _fetch_git("anthropics/claude-plugins-official")
    assert catalog is not None
    assert catalog["name"] == "m"
    assert local is not None
    # clone URL should be normalized to full https
    clone_url = captured_cmd[0][-2]
    assert "https://github.com/anthropics/claude-plugins-official.git" in clone_url


def test_fetch_git_ssh_url_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.marketplace_service._MARKETPLACE_CACHE",
        tmp_path / "marketplace_cache",
    )
    catalog, ts, local = _fetch_git("git@github.com:x/y.git")
    assert catalog is None and ts is None and local is None


def test_fetch_git_clone_failure(tmp_path, monkeypatch):
    import subprocess

    monkeypatch.setattr(
        "app.services.marketplace_service._MARKETPLACE_CACHE",
        tmp_path / "marketplace_cache",
    )

    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(
            cmd, 128, stdout="", stderr="fatal: repository not found"
        )

    with patch("subprocess.run", side_effect=fake_run):
        catalog, ts, local = _fetch_git("owner/nonexistent-repo")
    assert catalog is None
    # local may be None or the dir path; both acceptable


def test_fetch_git_no_marketplace_json(tmp_path, monkeypatch):
    """Cloned repo without .claude-plugin/marketplace.json."""
    import subprocess

    monkeypatch.setattr(
        "app.services.marketplace_service._MARKETPLACE_CACHE",
        tmp_path / "marketplace_cache",
    )

    def fake_run(cmd, capture_output, text, timeout):
        target = Path(cmd[-1])
        target.mkdir(parents=True, exist_ok=True)
        # no .claude-plugin dir
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with patch("subprocess.run", side_effect=fake_run):
        catalog, ts, local = _fetch_git("owner/bare-repo")
    assert catalog is None
    assert local is not None  # dir exists but no marketplace.json


# ---------- _parse_skill_frontmatter ----------


def test_parse_skill_frontmatter_full(tmp_path):
    p = tmp_path / "SKILL.md"
    p.write_text(
        "---\nname: my-skill\ndescription: Hello\nversion: 1.2.3\n---\nBody"
    )
    name, desc, ver = _parse_skill_frontmatter(p)
    assert name == "my-skill"
    assert desc == "Hello"
    assert ver == "1.2.3"


def test_parse_skill_frontmatter_missing_name_falls_back_to_dir(tmp_path):
    d = tmp_path / "fallback-name"
    d.mkdir()
    p = d / "SKILL.md"
    p.write_text("---\ndescription: d\n---\nBody")
    name, desc, ver = _parse_skill_frontmatter(p)
    assert name == "fallback-name"
    assert desc == "d"
    assert ver == "0.0.0"


def test_parse_skill_frontmatter_no_frontmatter_raises(tmp_path):
    p = tmp_path / "SKILL.md"
    p.write_text("just body, no frontmatter")
    with pytest.raises(ValueError, match="frontmatter"):
        _parse_skill_frontmatter(p)


def test_parse_skill_frontmatter_malformed_raises(tmp_path):
    """Unclosed frontmatter (only one '---' delimiter) raises."""
    p = tmp_path / "SKILL.md"
    p.write_text("---\nname: x\nno closing delimiter")
    with pytest.raises(ValueError, match="malformed|frontmatter"):
        _parse_skill_frontmatter(p)
