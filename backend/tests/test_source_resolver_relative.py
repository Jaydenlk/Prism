"""Tests for RelativePathResolver — copy from marketplace local clone."""
import pytest

from app.services.source_resolver import (
    RelativePathResolver,
    SourceDownloadError,
)


@pytest.mark.asyncio
async def test_relative_path_copytree_success(tmp_path):
    mp = tmp_path / "mp"
    (mp / "plugins" / "foo").mkdir(parents=True)
    (mp / "plugins" / "foo" / "plugin.json").write_text("{}")
    target = tmp_path / "out"
    r = RelativePathResolver()
    await r.download(
        "./plugins/foo",
        target,
        marketplace_local_dir=mp,
        github_token=None,
    )
    assert (target / "plugin.json").exists()


@pytest.mark.asyncio
async def test_relative_path_rejects_traversal(tmp_path):
    mp = tmp_path / "mp"
    mp.mkdir()
    target = tmp_path / "out"
    r = RelativePathResolver()
    with pytest.raises(SourceDownloadError, match="Invalid path|traversal"):
        await r.download(
            "./../etc",
            target,
            marketplace_local_dir=mp,
            github_token=None,
        )


@pytest.mark.asyncio
async def test_relative_path_requires_marketplace_local(tmp_path):
    r = RelativePathResolver()
    with pytest.raises(SourceDownloadError, match="URL-based marketplaces"):
        await r.download(
            "./foo",
            tmp_path / "out",
            marketplace_local_dir=None,
            github_token=None,
        )
