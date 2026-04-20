"""Tests for GithubTarballResolver — GitHub REST API HTTPS tarball."""
import io
import tarfile

import httpx
import pytest
import respx

from app.services.source_resolver import (
    GithubTarballResolver,
    SourceDownloadError,
)


def _make_tarball_fixture() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        info = tarfile.TarInfo(name="owner-repo-deadbeef/plugin.json")
        payload = b'{"name":"p"}'
        info.size = len(payload)
        tf.addfile(info, io.BytesIO(payload))
    return buf.getvalue()


@pytest.mark.asyncio
@respx.mock
async def test_github_tarball_success(tmp_path):
    respx.get("https://api.github.com/repos/owner/repo/tarball/HEAD").mock(
        return_value=httpx.Response(200, content=_make_tarball_fixture())
    )
    r = GithubTarballResolver()
    target = tmp_path / "out"
    await r.download(
        {"source": "github", "repo": "owner/repo"},
        target,
        marketplace_local_dir=None,
        github_token=None,
    )
    assert (target / "plugin.json").exists()


@pytest.mark.asyncio
@respx.mock
async def test_github_tarball_uses_ref(tmp_path):
    respx.get(
        "https://api.github.com/repos/owner/repo/tarball/v1.0"
    ).mock(return_value=httpx.Response(200, content=_make_tarball_fixture()))
    r = GithubTarballResolver()
    await r.download(
        {"source": "github", "repo": "owner/repo", "ref": "v1.0"},
        tmp_path / "out",
        marketplace_local_dir=None,
        github_token=None,
    )


@pytest.mark.asyncio
@respx.mock
async def test_github_tarball_429_rate_limit(tmp_path):
    respx.get("https://api.github.com/repos/owner/repo/tarball/HEAD").mock(
        return_value=httpx.Response(
            429,
            headers={"retry-after": "30", "x-ratelimit-remaining": "0"},
        )
    )
    r = GithubTarballResolver()
    with pytest.raises(SourceDownloadError, match="rate limit"):
        await r.download(
            {"source": "github", "repo": "owner/repo"},
            tmp_path / "out",
            marketplace_local_dir=None,
            github_token=None,
        )


@pytest.mark.asyncio
@respx.mock
async def test_github_tarball_401_auth(tmp_path):
    respx.get("https://api.github.com/repos/owner/repo/tarball/HEAD").mock(
        return_value=httpx.Response(401)
    )
    r = GithubTarballResolver()
    with pytest.raises(SourceDownloadError, match="Auth required"):
        await r.download(
            {"source": "github", "repo": "owner/repo"},
            tmp_path / "out",
            marketplace_local_dir=None,
            github_token=None,
        )
