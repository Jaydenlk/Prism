"""Tests for GitUrlResolver — git clone subprocess."""
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.services.source_resolver import (
    GitUrlResolver,
    SourceDownloadError,
)


@pytest.mark.asyncio
async def test_git_url_https_success(tmp_path):
    with patch(
        "app.services.source_resolver._run_subprocess", AsyncMock()
    ) as mock:
        r = GitUrlResolver()
        await r.download(
            {
                "source": "url",
                "url": "https://gitlab.com/x/y.git",
                "ref": "main",
            },
            tmp_path / "out",
            marketplace_local_dir=None,
            github_token=None,
        )
        args = mock.call_args_list[0][0][0]
        assert args[0:3] == ["git", "clone", "--depth"]
        assert "--branch" in args and "main" in args
        assert "https://gitlab.com/x/y.git" in args


@pytest.mark.asyncio
async def test_git_url_ssh_rejected(tmp_path):
    r = GitUrlResolver()
    with pytest.raises(SourceDownloadError, match="SSH URL unsupported"):
        await r.download(
            {"source": "url", "url": "git@github.com:x/y.git"},
            tmp_path / "out",
            marketplace_local_dir=None,
            github_token=None,
        )


@pytest.mark.asyncio
async def test_git_url_with_sha_pin(tmp_path):
    with patch(
        "app.services.source_resolver._run_subprocess", AsyncMock()
    ) as mock:
        r = GitUrlResolver()
        await r.download(
            {"source": "url", "url": "https://x/y.git", "sha": "a" * 40},
            tmp_path / "out",
            marketplace_local_dir=None,
            github_token=None,
        )
        # Should be 2 calls: clone + checkout sha
        assert mock.call_count == 2
        checkout_args = mock.call_args_list[1][0][0]
        assert checkout_args == ["git", "checkout", "a" * 40]
