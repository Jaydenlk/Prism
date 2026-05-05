"""Unit tests for 7 built-in action tools."""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import httpx
import pytest
import respx

from executor.tools.builtin.bash import BashTool
from executor.tools.builtin.edit import EditTool
from executor.tools.builtin.glob import GlobTool
from executor.tools.builtin.grep import GrepTool
from executor.tools.builtin.read import ReadTool
from executor.tools.builtin.web_fetch import WebFetchTool
from executor.tools.builtin.write import WriteTool


# ---------------------------------------------------------------------------
# ReadTool
# ---------------------------------------------------------------------------


class TestReadTool:
    tool = ReadTool()

    def test_name_description_schema(self):
        assert self.tool.name == "Read"
        assert self.tool.description
        assert self.tool.input_schema["required"] == ["path"]

    async def test_happy_reads_content_with_line_numbers(self, tmp_path: Path):
        f = tmp_path / "hello.txt"
        f.write_text("line one\nline two\nline three\n", encoding="utf-8")
        result = await self.tool.execute({"path": str(f)})
        assert not result.is_error
        assert "     1\tline one" in result.content
        assert "     2\tline two" in result.content

    async def test_happy_offset_and_limit(self, tmp_path: Path):
        f = tmp_path / "multi.txt"
        f.write_text("\n".join(f"line{i}" for i in range(1, 11)), encoding="utf-8")
        result = await self.tool.execute({"path": str(f), "offset": 3, "limit": 2})
        assert not result.is_error
        assert "     3\tline3" in result.content
        assert "     4\tline4" in result.content
        assert "line5" not in result.content

    async def test_error_file_not_found(self, tmp_path: Path):
        result = await self.tool.execute({"path": str(tmp_path / "missing.txt")})
        assert result.is_error
        assert "not found" in result.content.lower()

    async def test_error_path_is_directory(self, tmp_path: Path):
        result = await self.tool.execute({"path": str(tmp_path)})
        assert result.is_error
        assert "directory" in result.content.lower()

    async def test_empty_range_returns_message(self, tmp_path: Path):
        f = tmp_path / "short.txt"
        f.write_text("only one line\n", encoding="utf-8")
        result = await self.tool.execute({"path": str(f), "offset": 999})
        assert not result.is_error
        assert "empty range" in result.content


# ---------------------------------------------------------------------------
# WriteTool
# ---------------------------------------------------------------------------


class TestWriteTool:
    tool = WriteTool()

    def test_name_description_schema(self):
        assert self.tool.name == "Write"
        assert self.tool.description
        assert set(self.tool.input_schema["required"]) == {"path", "content"}

    async def test_happy_creates_file(self, tmp_path: Path):
        target = tmp_path / "out.txt"
        result = await self.tool.execute({"path": str(target), "content": "hello world"})
        assert not result.is_error
        assert target.read_text(encoding="utf-8") == "hello world"
        assert "bytes" in result.content

    async def test_happy_creates_parent_dirs(self, tmp_path: Path):
        target = tmp_path / "a" / "b" / "c.txt"
        result = await self.tool.execute({"path": str(target), "content": "nested"})
        assert not result.is_error
        assert target.exists()

    async def test_happy_empty_content_truncates(self, tmp_path: Path):
        target = tmp_path / "existing.txt"
        target.write_text("old content", encoding="utf-8")
        result = await self.tool.execute({"path": str(target), "content": ""})
        assert not result.is_error
        assert target.read_text(encoding="utf-8") == ""

    async def test_error_missing_path(self):
        result = await self.tool.execute({"content": "x"})
        assert result.is_error
        assert "path" in result.content.lower()

    async def test_error_missing_content(self, tmp_path: Path):
        result = await self.tool.execute({"path": str(tmp_path / "x.txt")})
        assert result.is_error
        assert "content" in result.content.lower()


# ---------------------------------------------------------------------------
# EditTool
# ---------------------------------------------------------------------------


class TestEditTool:
    tool = EditTool()

    def test_name_description_schema(self):
        assert self.tool.name == "Edit"
        assert self.tool.description
        assert set(self.tool.input_schema["required"]) == {"path", "old_string", "new_string"}

    async def test_happy_replaces_single_occurrence(self, tmp_path: Path):
        f = tmp_path / "code.py"
        f.write_text("foo = 1\nbar = 2\n", encoding="utf-8")
        result = await self.tool.execute(
            {"path": str(f), "old_string": "foo = 1", "new_string": "foo = 99"}
        )
        assert not result.is_error
        assert f.read_text(encoding="utf-8") == "foo = 99\nbar = 2\n"

    async def test_happy_replace_all(self, tmp_path: Path):
        f = tmp_path / "dup.py"
        f.write_text("x = 1\nx = 1\nx = 1\n", encoding="utf-8")
        result = await self.tool.execute(
            {"path": str(f), "old_string": "x = 1", "new_string": "x = 2", "replace_all": True}
        )
        assert not result.is_error
        assert "3" in result.content
        assert f.read_text(encoding="utf-8") == "x = 2\nx = 2\nx = 2\n"

    async def test_error_old_equals_new(self, tmp_path: Path):
        f = tmp_path / "same.txt"
        f.write_text("a = 1\n", encoding="utf-8")
        result = await self.tool.execute(
            {"path": str(f), "old_string": "a = 1", "new_string": "a = 1"}
        )
        assert result.is_error
        assert "differ" in result.content.lower()

    async def test_error_old_string_not_found(self, tmp_path: Path):
        f = tmp_path / "missing.txt"
        f.write_text("hello\n", encoding="utf-8")
        result = await self.tool.execute(
            {"path": str(f), "old_string": "nonexistent", "new_string": "x"}
        )
        assert result.is_error
        assert "not found" in result.content.lower()

    async def test_error_multi_match_without_replace_all(self, tmp_path: Path):
        f = tmp_path / "dup.txt"
        f.write_text("a\na\na\n", encoding="utf-8")
        result = await self.tool.execute(
            {"path": str(f), "old_string": "a", "new_string": "b"}
        )
        assert result.is_error
        assert "3" in result.content


# ---------------------------------------------------------------------------
# BashTool
# ---------------------------------------------------------------------------


class TestBashTool:
    tool = BashTool()

    def test_name_description_schema(self):
        assert self.tool.name == "Bash"
        assert self.tool.description
        assert self.tool.input_schema["required"] == ["command"]

    async def test_happy_echo(self):
        result = await self.tool.execute({"command": "python -c \"print('hello')\"" })
        assert not result.is_error
        assert "hello" in result.content

    async def test_happy_nonzero_exit_is_error(self):
        result = await self.tool.execute(
            {"command": "python -c \"import sys; sys.exit(1)\""}
        )
        assert result.is_error
        assert "exit 1" in result.content

    async def test_error_timeout(self):
        result = await self.tool.execute(
            {"command": "python -c \"import time; time.sleep(10)\"", "timeout_s": 1}
        )
        assert result.is_error
        assert "timed out" in result.content.lower()

    async def test_error_invalid_cwd(self):
        result = await self.tool.execute(
            {"command": "python -c \"print('x')\"", "cwd": "/nonexistent/path/12345"}
        )
        assert result.is_error
        assert "cwd" in result.content.lower()

    async def test_happy_cwd_respected(self, tmp_path: Path):
        result = await self.tool.execute(
            {"command": "python -c \"import os; print(os.getcwd())\"", "cwd": str(tmp_path)}
        )
        assert not result.is_error
        # Use resolve() to normalize case on Windows
        assert Path(result.content.strip()).resolve() == tmp_path.resolve()


# ---------------------------------------------------------------------------
# GlobTool
# ---------------------------------------------------------------------------


class TestGlobTool:
    tool = GlobTool()

    def test_name_description_schema(self):
        assert self.tool.name == "Glob"
        assert self.tool.description
        assert self.tool.input_schema["required"] == ["pattern"]

    async def test_happy_finds_files(self, tmp_path: Path):
        (tmp_path / "a.py").write_text("", encoding="utf-8")
        (tmp_path / "b.py").write_text("", encoding="utf-8")
        (tmp_path / "c.txt").write_text("", encoding="utf-8")
        result = await self.tool.execute({"pattern": "*.py", "path": str(tmp_path)})
        assert not result.is_error
        assert "a.py" in result.content
        assert "b.py" in result.content
        assert "c.txt" not in result.content

    async def test_happy_mtime_ordering(self, tmp_path: Path):
        older = tmp_path / "older.py"
        newer = tmp_path / "newer.py"
        older.write_text("", encoding="utf-8")
        time.sleep(0.05)
        newer.write_text("", encoding="utf-8")
        # Force distinct mtimes
        os.utime(str(older), (time.time() - 10, time.time() - 10))
        os.utime(str(newer), (time.time(), time.time()))
        result = await self.tool.execute({"pattern": "*.py", "path": str(tmp_path)})
        assert not result.is_error
        newer_pos = result.content.index("newer.py")
        older_pos = result.content.index("older.py")
        assert newer_pos < older_pos

    async def test_happy_no_matches(self, tmp_path: Path):
        result = await self.tool.execute({"pattern": "*.xyz", "path": str(tmp_path)})
        assert not result.is_error
        assert "no files match" in result.content.lower()

    async def test_error_path_not_directory(self, tmp_path: Path):
        f = tmp_path / "file.txt"
        f.write_text("", encoding="utf-8")
        result = await self.tool.execute({"pattern": "*.txt", "path": str(f)})
        assert result.is_error
        assert "not a directory" in result.content.lower()


# ---------------------------------------------------------------------------
# GrepTool
# ---------------------------------------------------------------------------


class TestGrepTool:
    tool = GrepTool()

    def test_name_description_schema(self):
        assert self.tool.name == "Grep"
        assert self.tool.description
        assert self.tool.input_schema["required"] == ["pattern"]

    async def test_happy_finds_pattern(self, tmp_path: Path):
        f = tmp_path / "sample.py"
        f.write_text("def hello():\n    pass\n", encoding="utf-8")
        result = await self.tool.execute({"pattern": "def hello", "path": str(tmp_path)})
        assert not result.is_error
        assert "hello" in result.content

    async def test_happy_no_matches(self, tmp_path: Path):
        f = tmp_path / "empty.py"
        f.write_text("x = 1\n", encoding="utf-8")
        result = await self.tool.execute({"pattern": "nonexistent_pattern_xyz", "path": str(tmp_path)})
        assert not result.is_error
        assert "no matches" in result.content.lower()

    async def test_happy_python_fallback_finds_pattern(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("executor.tools.builtin.grep.shutil.which", lambda _: None)
        f = tmp_path / "code.py"
        f.write_text("import os\nimport sys\n", encoding="utf-8")
        result = await self.tool.execute({"pattern": "import", "path": str(tmp_path)})
        assert not result.is_error
        assert "import" in result.content

    async def test_happy_python_fallback_no_matches(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("executor.tools.builtin.grep.shutil.which", lambda _: None)
        f = tmp_path / "data.txt"
        f.write_text("hello world\n", encoding="utf-8")
        result = await self.tool.execute({"pattern": "zzz_not_here", "path": str(tmp_path)})
        assert not result.is_error
        assert "no matches" in result.content.lower()

    async def test_happy_python_fallback_case_insensitive(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("executor.tools.builtin.grep.shutil.which", lambda _: None)
        f = tmp_path / "ci.txt"
        f.write_text("Hello World\n", encoding="utf-8")
        result = await self.tool.execute(
            {"pattern": "hello", "path": str(tmp_path), "case_insensitive": True}
        )
        assert not result.is_error
        assert "Hello" in result.content

    async def test_error_invalid_regex_python_fallback(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("executor.tools.builtin.grep.shutil.which", lambda _: None)
        result = await self.tool.execute({"pattern": "[invalid", "path": str(tmp_path)})
        assert result.is_error
        assert "invalid regex" in result.content.lower()


# ---------------------------------------------------------------------------
# WebFetchTool
# ---------------------------------------------------------------------------


class TestWebFetchTool:
    tool = WebFetchTool()

    def test_name_description_schema(self):
        assert self.tool.name == "WebFetch"
        assert self.tool.description
        assert self.tool.input_schema["required"] == ["url"]

    @respx.mock
    async def test_happy_plain_text(self):
        respx.get("https://example.com/data").mock(
            return_value=httpx.Response(200, text="plain response", headers={"content-type": "text/plain"})
        )
        result = await self.tool.execute({"url": "https://example.com/data"})
        assert not result.is_error
        assert "plain response" in result.content
        assert "200" in result.content

    @respx.mock
    async def test_happy_html_stripped(self):
        html = "<html><body><h1>Hello</h1><p>World</p></body></html>"
        respx.get("https://example.com/page").mock(
            return_value=httpx.Response(
                200, text=html, headers={"content-type": "text/html; charset=utf-8"}
            )
        )
        result = await self.tool.execute({"url": "https://example.com/page"})
        assert not result.is_error
        assert "<html>" not in result.content
        assert "Hello" in result.content
        assert "World" in result.content

    @respx.mock
    async def test_error_http_4xx(self):
        respx.get("https://example.com/missing").mock(
            return_value=httpx.Response(404, text="not found", headers={"content-type": "text/plain"})
        )
        result = await self.tool.execute({"url": "https://example.com/missing"})
        assert result.is_error
        assert "404" in result.content

    async def test_error_non_http_url(self):
        result = await self.tool.execute({"url": "ftp://example.com/file"})
        assert result.is_error
        assert "http" in result.content.lower()

    async def test_error_missing_url(self):
        result = await self.tool.execute({})
        assert result.is_error
        assert "url" in result.content.lower()

    @respx.mock
    async def test_error_network_failure(self):
        respx.get("https://unreachable.example.com/").mock(
            side_effect=httpx.ConnectError("connection refused")
        )
        result = await self.tool.execute({"url": "https://unreachable.example.com/"})
        assert result.is_error
        assert "fetch failed" in result.content.lower()
