"""Tests for _safe_extract_tar — CVE-2025-4517 defense (filter='data' + realpath check)."""
from pathlib import Path
import io
import tarfile
import pytest

from app.services.source_resolver import _safe_extract_tar


def _make_tar_with_members(members: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, content in members:
            info = tarfile.TarInfo(name=name)
            info.size = len(content)
            tf.addfile(info, io.BytesIO(content))
    return buf.getvalue()


def test_extract_normal_content(tmp_path):
    tar_bytes = _make_tar_with_members([("repo-abc/README.md", b"hi")])
    tar_file = tmp_path / "t.tar.gz"
    tar_file.write_bytes(tar_bytes)
    target = tmp_path / "out"
    _safe_extract_tar(tar_file, target, strip_root_dir=True)
    assert (target / "README.md").read_text() == "hi"


def test_extract_absolute_path_rewritten_to_relative(tmp_path):
    """Python 3.12 data_filter strips leading '/' (documented behavior),
    so an absolute path entry is extracted AS RELATIVE inside target_dir,
    never escaping. This is the defense — no file created at /etc."""
    tar_bytes = _make_tar_with_members([("/etc/evil", b"bad")])
    tar_file = tmp_path / "t.tar.gz"
    tar_file.write_bytes(tar_bytes)
    target = tmp_path / "out"
    _safe_extract_tar(tar_file, target, strip_root_dir=False)
    # file extracted under target_dir/etc/evil (leading / stripped)
    assert (target / "etc" / "evil").read_bytes() == b"bad"
    # /etc/evil itself was NOT created on the filesystem
    import os
    assert not os.path.exists("/etc/evil")


def test_extract_rejects_parent_traversal(tmp_path):
    tar_bytes = _make_tar_with_members([("../../escape", b"bad")])
    tar_file = tmp_path / "t.tar.gz"
    tar_file.write_bytes(tar_bytes)
    target = tmp_path / "out"
    with pytest.raises((tarfile.ExtractError, tarfile.OutsideDestinationError)):
        _safe_extract_tar(tar_file, target, strip_root_dir=False)


def test_strip_root_dir_flattens(tmp_path):
    tar_bytes = _make_tar_with_members(
        [
            ("owner-repo-deadbeef/plugin.json", b"{}"),
            ("owner-repo-deadbeef/skills/foo/SKILL.md", b"---\n---\nbody"),
        ]
    )
    tar_file = tmp_path / "t.tar.gz"
    tar_file.write_bytes(tar_bytes)
    target = tmp_path / "out"
    _safe_extract_tar(tar_file, target, strip_root_dir=True)
    assert (target / "plugin.json").exists()
    assert (target / "skills" / "foo" / "SKILL.md").exists()
