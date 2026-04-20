"""Verify git binary is available (required by GitUrlResolver / GitSubdirResolver)."""
import shutil


def test_git_binary_on_path():
    assert shutil.which("git") is not None, "git binary missing — check Dockerfile"
