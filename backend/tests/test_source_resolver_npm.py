"""Tests for NpmResolver — packument + tarball two-stage."""
import io
import tarfile

import httpx
import pytest
import respx

from app.services.source_resolver import (
    NpmResolver,
    SourceDownloadError,
)


def _make_npm_tgz() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        info = tarfile.TarInfo(name="package/plugin.json")
        payload = b'{"name":"x"}'
        info.size = len(payload)
        tf.addfile(info, io.BytesIO(payload))
    return buf.getvalue()


@pytest.mark.asyncio
@respx.mock
async def test_npm_exact_version(tmp_path):
    respx.get("https://registry.npmjs.org/pkg").mock(
        return_value=httpx.Response(
            200,
            json={
                "dist-tags": {"latest": "1.2.3"},
                "versions": {
                    "1.2.3": {
                        "dist": {
                            "tarball": "https://registry.npmjs.org/pkg/-/pkg-1.2.3.tgz"
                        }
                    }
                },
            },
        )
    )
    respx.get("https://registry.npmjs.org/pkg/-/pkg-1.2.3.tgz").mock(
        return_value=httpx.Response(200, content=_make_npm_tgz())
    )
    r = NpmResolver()
    await r.download(
        {"source": "npm", "package": "pkg", "version": "1.2.3"},
        tmp_path / "out",
        None,
        None,
    )
    assert (tmp_path / "out" / "plugin.json").exists()


@pytest.mark.asyncio
@respx.mock
async def test_npm_scoped_package_url_encoded(tmp_path):
    respx.get("https://registry.npmjs.org/@org%2Fpkg").mock(
        return_value=httpx.Response(
            200,
            json={
                "dist-tags": {"latest": "2.0.0"},
                "versions": {
                    "2.0.0": {
                        "dist": {
                            "tarball": "https://registry.npmjs.org/@org%2Fpkg/-/pkg-2.0.0.tgz"
                        }
                    }
                },
            },
        )
    )
    respx.get(
        "https://registry.npmjs.org/@org%2Fpkg/-/pkg-2.0.0.tgz"
    ).mock(return_value=httpx.Response(200, content=_make_npm_tgz()))
    r = NpmResolver()
    await r.download(
        {"source": "npm", "package": "@org/pkg"},
        tmp_path / "out",
        None,
        None,
    )


@pytest.mark.asyncio
@respx.mock
async def test_npm_404_package(tmp_path):
    respx.get("https://registry.npmjs.org/missing").mock(
        return_value=httpx.Response(404)
    )
    r = NpmResolver()
    with pytest.raises(SourceDownloadError, match="not found"):
        await r.download(
            {"source": "npm", "package": "missing"},
            tmp_path / "out",
            None,
            None,
        )


@pytest.mark.asyncio
@respx.mock
async def test_npm_range_fallback_to_latest(tmp_path):
    """If version is a range like '^2.0.0' (not exact), fall back to latest."""
    respx.get("https://registry.npmjs.org/pkg").mock(
        return_value=httpx.Response(
            200,
            json={
                "dist-tags": {"latest": "2.1.0"},
                "versions": {
                    "2.0.0": {"dist": {"tarball": "https://x/a.tgz"}},
                    "2.1.0": {
                        "dist": {
                            "tarball": "https://registry.npmjs.org/pkg/-/pkg-2.1.0.tgz"
                        }
                    },
                },
            },
        )
    )
    respx.get("https://registry.npmjs.org/pkg/-/pkg-2.1.0.tgz").mock(
        return_value=httpx.Response(200, content=_make_npm_tgz())
    )
    r = NpmResolver()
    await r.download(
        {"source": "npm", "package": "pkg", "version": "^2.0.0"},
        tmp_path / "out",
        None,
        None,
    )
