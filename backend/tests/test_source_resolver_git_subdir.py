"""Tests for GitSubdirResolver — cone-mode sparse checkout."""
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.services.source_resolver import (
    GitSubdirResolver,
    SourceDownloadError,
)


@pytest.mark.asyncio
async def test_git_subdir_shorthand_normalizes(tmp_path):
    """'owner/repo' shorthand → https://github.com/owner/repo.git"""
    target = tmp_path / "out"

    async def fake_run(cmd, **kw):
        if "clone" in cmd:
            # simulate clone creating target_dir
            Path(cmd[-1]).mkdir(parents=True, exist_ok=True)
        # simulate sparse-checkout + checkout placing files
        if "checkout" in cmd and len(cmd) == 2:
            sub = (Path(kw.get("cwd", ".")) / "tools" / "cp")
            sub.mkdir(parents=True, exist_ok=True)
            (sub / "plugin.json").write_text("{}")

    with patch(
        "app.services.source_resolver._run_subprocess",
        AsyncMock(side_effect=fake_run),
    ) as mock:
        r = GitSubdirResolver()
        await r.download(
            {"source": "git-subdir", "url": "owner/repo", "path": "tools/cp"},
            target,
            marketplace_local_dir=None,
            github_token=None,
        )
        clone_cmd = mock.call_args_list[0][0][0]
        assert "https://github.com/owner/repo.git" in clone_cmd
        assert "--filter=blob:none" in clone_cmd
        assert "--no-checkout" in clone_cmd


@pytest.mark.asyncio
async def test_git_subdir_path_missing_after_checkout(tmp_path):
    """If path doesn't exist after checkout, raise."""

    async def noop(cmd, **kw):
        if "clone" in cmd:
            Path(cmd[-1]).mkdir(parents=True, exist_ok=True)

    with patch(
        "app.services.source_resolver._run_subprocess",
        AsyncMock(side_effect=noop),
    ):
        r = GitSubdirResolver()
        with pytest.raises(SourceDownloadError, match="path not found"):
            await r.download(
                {
                    "source": "git-subdir",
                    "url": "owner/repo",
                    "path": "missing/dir",
                },
                tmp_path / "out",
                marketplace_local_dir=None,
                github_token=None,
            )


@pytest.mark.asyncio
async def test_git_subdir_ssh_rejected(tmp_path):
    r = GitSubdirResolver()
    with pytest.raises(SourceDownloadError, match="SSH"):
        await r.download(
            {
                "source": "git-subdir",
                "url": "git@github.com:x/y.git",
                "path": "p",
            },
            tmp_path / "out",
            None,
            None,
        )


@pytest.mark.asyncio
async def test_git_subdir_with_sha(tmp_path):
    async def fake(cmd, **kw):
        if "clone" in cmd:
            Path(cmd[-1]).mkdir(parents=True, exist_ok=True)
        if "checkout" in cmd and len(cmd) > 2:
            # sha checkout
            sub = Path(kw["cwd"]) / "p"
            sub.mkdir(parents=True, exist_ok=True)

    with patch(
        "app.services.source_resolver._run_subprocess",
        AsyncMock(side_effect=fake),
    ) as m:
        r = GitSubdirResolver()
        await r.download(
            {
                "source": "git-subdir",
                "url": "x/y",
                "path": "p",
                "sha": "a" * 40,
            },
            tmp_path / "out",
            None,
            None,
        )
        # Find the checkout call with sha
        checkouts = [
            c[0][0] for c in m.call_args_list if "checkout" in c[0][0]
        ]
        assert any("a" * 40 in cmd for cmd in checkouts)
