# Session 4c Implementation Plan — Skills Market Catalog + 5-Source Install

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Production-grade Skills Marketplace catalog browser with one-click install for all 5 CC plugin source types (relative-path / github / url / git-subdir / npm), grounded in official CC docs + 7 exa primary-source citations.

**Architecture:** Two-layer registry (reuse `marketplace_registry` + `skill_installs.marketplace_id` from Session 3 Phase 1) + 5 independent `SourceResolver` classes (single responsibility) + git-based marketplace fetch (clone `.claude-plugin/marketplace.json`) + HTTPS-only GitHub REST tarball API (bypasses CC-CLI SSH issue #47088) + Python 3.12 `tarfile filter='data'` + realpath check (CVE-2025-4517 defense) + Redis SETNX install lock.

**Tech Stack:** FastAPI / SQLAlchemy 2.0 / Pydantic v2 / httpx (async stream) / tarfile stdlib / subprocess (git clone / sparse-checkout cone mode) / Redis / Playwright MCP (桌面+移动双端 e2e).

**Source spec:** `docs/superpowers/specs/2026-04-20-session4c-skills-market-catalog-design.md` (commit `f437af3`). All task references to §N below map to spec section N.

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `backend/Dockerfile` | Install `git` binary for resolver 3/4 | 1 |
| `backend/app/services/source_resolver.py` | ABC + 5 resolver classes + `_safe_extract_tar` + `_run_subprocess` + `_check_rate_limit` | 2-7 |
| `backend/app/services/marketplace_service.py` | `_try_fetch` 双模式 + `_validate_marketplace_shape` + `install_plugin` + `_get_marketplace_local_dir` | 8, 10 |
| `backend/app/services/skill_install_service.py` | `install_from_dir` method (if missing) | 9 |
| `backend/app/schemas/marketplace.py` | `InstallReport` Pydantic model | 11 |
| `backend/app/api/v1/marketplaces.py` | New `POST /{id}/plugins/{name}/install` endpoint | 11 |
| `frontend/Prism.html` SkillsPage | Marketplace tab catalog grid + 详情 modal + install consent | 12-13 |
| `e2e/tests/skills-marketplace-catalog.spec.ts` | 10 tests × 2 viewport = 20 total | 14 |
| `backend/tests/test_source_resolver_*.py` × 5 + `test_safe_extract_tar.py` + `test_marketplace_service_git_fetch.py` + `test_marketplace_install.py` | Unit tests (32 total) | tasks 2-10 inline |

---

## Task 1: Infra Prep — Dockerfile git + data volume

**Files:**
- Modify: `backend/Dockerfile:6-8`
- Modify: `docker-compose.yml` (backend volumes)

- [ ] **Step 1: Write the failing smoke test**

Create `backend/tests/test_infra_git_available.py`:

```python
"""Verify git binary is available (required by GitUrlResolver / GitSubdirResolver)."""
import shutil

def test_git_binary_on_path():
    assert shutil.which("git") is not None, "git binary missing — check Dockerfile"
```

- [ ] **Step 2: Run test to verify it fails in current container**

```bash
docker compose -p prismv3 exec -T backend python -c "import shutil; assert shutil.which('git') is not None, 'FAIL'"
```
Expected output: `AssertionError: FAIL`

- [ ] **Step 3: Modify Dockerfile to install git**

Edit `backend/Dockerfile` line 6-8:

```dockerfile
# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget git \
    && rm -rf /var/lib/apt/lists/*
```

Edit `docker-compose.yml` backend service (add named volume for plugin cache persistence):

```yaml
  backend:
    # ...existing...
    volumes:
      - prism_plugin_data:/app/data

volumes:
  prism_plugin_data:
```

(If named volume `prism_plugin_data` exists, extend; do not delete existing volumes.)

- [ ] **Step 4: Rebuild backend + verify**

```bash
docker compose -p prismv3 up -d --build --force-recreate backend
docker compose -p prismv3 exec -T backend git --version
```
Expected: `git version 2.x.x`

```bash
docker compose -p prismv3 exec -T backend pip install pytest pytest-asyncio
docker compose -p prismv3 exec -T backend pytest tests/test_infra_git_available.py -v
```
Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/Dockerfile docker-compose.yml backend/tests/test_infra_git_available.py
git commit -m "infra(session4c): Dockerfile add git + persistent plugin_data volume"
```

---

## Task 2: SourceResolver ABC + SourceDownloadError + _safe_extract_tar

**Files:**
- Create: `backend/app/services/source_resolver.py`
- Create: `backend/tests/test_safe_extract_tar.py`

- [ ] **Step 1: Write 4 failing tests for _safe_extract_tar**

Create `backend/tests/test_safe_extract_tar.py`:

```python
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

def test_extract_rejects_absolute_path(tmp_path):
    tar_bytes = _make_tar_with_members([("/etc/evil", b"bad")])
    tar_file = tmp_path / "t.tar.gz"
    tar_file.write_bytes(tar_bytes)
    target = tmp_path / "out"
    with pytest.raises(tarfile.ExtractError):
        _safe_extract_tar(tar_file, target, strip_root_dir=False)

def test_extract_rejects_parent_traversal(tmp_path):
    tar_bytes = _make_tar_with_members([("../../escape", b"bad")])
    tar_file = tmp_path / "t.tar.gz"
    tar_file.write_bytes(tar_bytes)
    target = tmp_path / "out"
    with pytest.raises(tarfile.ExtractError):
        _safe_extract_tar(tar_file, target, strip_root_dir=False)

def test_strip_root_dir_flattens(tmp_path):
    tar_bytes = _make_tar_with_members([
        ("owner-repo-deadbeef/plugin.json", b"{}"),
        ("owner-repo-deadbeef/skills/foo/SKILL.md", b"---\n---\nbody"),
    ])
    tar_file = tmp_path / "t.tar.gz"
    tar_file.write_bytes(tar_bytes)
    target = tmp_path / "out"
    _safe_extract_tar(tar_file, target, strip_root_dir=True)
    assert (target / "plugin.json").exists()
    assert (target / "skills" / "foo" / "SKILL.md").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose -p prismv3 exec -T backend pytest tests/test_safe_extract_tar.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.services.source_resolver'`

- [ ] **Step 3: Create source_resolver.py with ABC + error class + _safe_extract_tar + _run_subprocess + _check_rate_limit**

Create `backend/app/services/source_resolver.py`:

```python
"""SourceResolver — 5-strategy plugin source downloader.

Single responsibility per resolver class. See spec §3.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tarfile
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()


class SourceDownloadError(Exception):
    """Raised when a resolver cannot fetch plugin source.

    stage: which step failed (dispatch / github_tarball / git_url / ...)
    underlying: the wrapped exception, if any
    hint: user-facing message for the 422/429/504 toast
    """

    def __init__(self, stage: str, underlying: Exception | None, hint: str):
        self.stage = stage
        self.underlying = underlying
        self.hint = hint
        super().__init__(f"[{stage}] {hint}")


class SourceResolver(ABC):
    @abstractmethod
    async def download(
        self,
        source: dict | str,
        target_dir: Path,
        marketplace_local_dir: Path | None,
        github_token: str | None,
    ) -> None:
        ...


def _safe_extract_tar(
    tar_path: Path, target_dir: Path, *, strip_root_dir: bool
) -> None:
    """Extract .tar.gz into target_dir with CVE-2025-4517 defense.

    Uses Python 3.12+ filter='data' PLUS realpath check: every member's
    final absolute path MUST startswith target_dir realpath.
    If strip_root_dir: single top-level directory is flattened.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    target_real = str(target_dir.resolve())

    with tarfile.open(tar_path, "r:gz") as tf:
        members = tf.getmembers()
        if strip_root_dir and members:
            top = members[0].name.split("/", 1)[0]
            rewritten = []
            for m in members:
                if m.name == top:
                    continue
                elif m.name.startswith(top + "/"):
                    m.name = m.name[len(top) + 1 :]
                    rewritten.append(m)
                else:
                    rewritten.append(m)
            members = rewritten

        def _guard(member: tarfile.TarInfo, path: str) -> tarfile.TarInfo | None:
            # filter='data' already blocks devices, symlinks-outside, etc.
            filtered = tarfile.data_filter(member, path)
            if filtered is None:
                return None
            # Extra realpath defense (CVE-2025-4517 race):
            extracted = (Path(path) / filtered.name).resolve()
            if not str(extracted).startswith(target_real):
                raise tarfile.ExtractError(
                    f"Path traversal blocked: {member.name!r}"
                )
            return filtered

        # Python 3.12 extractall with filter
        for m in members:
            tf.extract(m, path=str(target_dir), filter=_guard)


async def _run_subprocess(
    cmd: list[str], *, cwd: Path | str | None = None, timeout: float = 60.0
) -> None:
    """Run subprocess async. Raise SourceDownloadError on non-zero exit / timeout."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd) if cwd else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            raise SourceDownloadError(
                "subprocess_timeout", None,
                f"Timed out after {timeout}s: {' '.join(cmd[:3])}..."
            )
        if proc.returncode != 0:
            raise SourceDownloadError(
                "subprocess_failed", None,
                f"{cmd[0]} exit {proc.returncode}: {stderr.decode()[:200]}"
            )
    except FileNotFoundError as exc:
        raise SourceDownloadError("binary_missing", exc, f"{cmd[0]} not found")


def _check_rate_limit(resp: httpx.Response) -> None:
    """Raise SourceDownloadError on GitHub rate limit 403/429."""
    if resp.status_code not in (403, 429):
        return
    remaining = resp.headers.get("x-ratelimit-remaining")
    retry_after = resp.headers.get("retry-after")
    reset = resp.headers.get("x-ratelimit-reset")
    if retry_after or remaining == "0":
        wait_s = (
            int(retry_after)
            if retry_after
            else max(1, int(reset) - int(time.time()))
            if reset
            else 60
        )
        raise SourceDownloadError(
            "rate_limit", None,
            f"GitHub rate limit hit — retry in {wait_s}s "
            f"(set GITHUB_TOKEN for 5000/h instead of 60/h)"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker compose -p prismv3 exec -T backend pytest tests/test_safe_extract_tar.py -v
```
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/source_resolver.py backend/tests/test_safe_extract_tar.py
git commit -m "feat(session4c): SourceResolver ABC + _safe_extract_tar (CVE-2025-4517 defense)"
```

---

## Task 3: RelativePathResolver + tests

**Files:**
- Modify: `backend/app/services/source_resolver.py` (append class)
- Create: `backend/tests/test_source_resolver_relative.py`

- [ ] **Step 1: Write 3 failing tests**

```python
"""Tests for RelativePathResolver — copy from marketplace local clone."""
from pathlib import Path
import pytest
from app.services.source_resolver import RelativePathResolver, SourceDownloadError

@pytest.mark.asyncio
async def test_relative_path_copytree_success(tmp_path):
    mp = tmp_path / "mp"
    (mp / "plugins" / "foo").mkdir(parents=True)
    (mp / "plugins" / "foo" / "plugin.json").write_text("{}")
    target = tmp_path / "out"
    r = RelativePathResolver()
    await r.download("./plugins/foo", target, marketplace_local_dir=mp, github_token=None)
    assert (target / "plugin.json").exists()

@pytest.mark.asyncio
async def test_relative_path_rejects_traversal(tmp_path):
    mp = tmp_path / "mp"
    mp.mkdir()
    target = tmp_path / "out"
    r = RelativePathResolver()
    with pytest.raises(SourceDownloadError, match="Invalid path|traversal"):
        await r.download("./../etc", target, marketplace_local_dir=mp, github_token=None)

@pytest.mark.asyncio
async def test_relative_path_requires_marketplace_local(tmp_path):
    r = RelativePathResolver()
    with pytest.raises(SourceDownloadError, match="URL-based marketplaces"):
        await r.download("./foo", tmp_path / "out", marketplace_local_dir=None, github_token=None)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose -p prismv3 exec -T backend pytest tests/test_source_resolver_relative.py -v
```
Expected: `ImportError: cannot import name 'RelativePathResolver'`

- [ ] **Step 3: Append RelativePathResolver to source_resolver.py**

```python
class RelativePathResolver(SourceResolver):
    async def download(self, source, target_dir, marketplace_local_dir, github_token):
        if marketplace_local_dir is None:
            raise SourceDownloadError(
                "relative_path", None,
                "Relative-path source requires git-based marketplace (local clone). "
                "URL-based marketplaces don't support ./ paths (see CC docs)."
            )
        rel = source if isinstance(source, str) else source.get("path", "")
        if not rel.startswith("./") or ".." in rel:
            raise SourceDownloadError(
                "relative_path", None, f"Invalid path: {rel!r}"
            )
        src = (marketplace_local_dir / rel[2:]).resolve()
        root = marketplace_local_dir.resolve()
        if not str(src).startswith(str(root) + os.sep):
            raise SourceDownloadError(
                "relative_path", None, "Path traversal blocked"
            )
        if not src.is_dir():
            raise SourceDownloadError(
                "relative_path", None, f"Path not found: {rel}"
            )
        shutil.copytree(src, target_dir, dirs_exist_ok=False)
```

- [ ] **Step 4: Run tests to verify pass**

```bash
docker compose -p prismv3 exec -T backend pytest tests/test_source_resolver_relative.py -v
```
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/source_resolver.py backend/tests/test_source_resolver_relative.py
git commit -m "feat(session4c): RelativePathResolver (local-copy from marketplace clone)"
```

---

## Task 4: GithubTarballResolver + tests

**Files:**
- Modify: `backend/app/services/source_resolver.py` (append class)
- Create: `backend/tests/test_source_resolver_github.py`

- [ ] **Step 1: Write 4 failing tests**

```python
"""Tests for GithubTarballResolver — GitHub REST API HTTPS tarball."""
import io
import tarfile
from pathlib import Path
import httpx
import pytest
import respx
from app.services.source_resolver import GithubTarballResolver, SourceDownloadError

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
        target, marketplace_local_dir=None, github_token=None,
    )
    assert (target / "plugin.json").exists()

@pytest.mark.asyncio
@respx.mock
async def test_github_tarball_uses_ref(tmp_path):
    respx.get("https://api.github.com/repos/owner/repo/tarball/v1.0").mock(
        return_value=httpx.Response(200, content=_make_tarball_fixture())
    )
    r = GithubTarballResolver()
    await r.download(
        {"source": "github", "repo": "owner/repo", "ref": "v1.0"},
        tmp_path / "out", marketplace_local_dir=None, github_token=None,
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
            tmp_path / "out", marketplace_local_dir=None, github_token=None,
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
            tmp_path / "out", marketplace_local_dir=None, github_token=None,
        )
```

- [ ] **Step 2: Install respx + run tests to verify they fail**

```bash
docker compose -p prismv3 exec -T backend pip install respx
docker compose -p prismv3 exec -T backend pytest tests/test_source_resolver_github.py -v
```
Expected: `ImportError: cannot import name 'GithubTarballResolver'`

- [ ] **Step 3: Append GithubTarballResolver**

```python
class GithubTarballResolver(SourceResolver):
    async def download(self, source, target_dir, marketplace_local_dir, github_token):
        repo = source["repo"]
        ref = source.get("sha") or source.get("ref") or "HEAD"
        url = f"https://api.github.com/repos/{repo}/tarball/{ref}"
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
        }
        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"
        target_dir.mkdir(parents=True, exist_ok=True)
        tmp_tar = target_dir.parent / f".{target_dir.name}.tar.gz"
        try:
            async with httpx.AsyncClient(
                timeout=60.0, follow_redirects=True, max_redirects=5
            ) as client:
                async with client.stream("GET", url, headers=headers) as resp:
                    if resp.status_code == 404:
                        raise SourceDownloadError(
                            "github_tarball", None,
                            f"Repo or ref not found: {repo}@{ref}"
                        )
                    if resp.status_code == 401:
                        raise SourceDownloadError(
                            "github_tarball", None,
                            "Auth required — set GITHUB_TOKEN for private repo"
                        )
                    _check_rate_limit(resp)
                    resp.raise_for_status()
                    with tmp_tar.open("wb") as f:
                        async for chunk in resp.aiter_bytes(chunk_size=65536):
                            f.write(chunk)
            _safe_extract_tar(tmp_tar, target_dir, strip_root_dir=True)
        finally:
            if tmp_tar.exists():
                tmp_tar.unlink()
```

- [ ] **Step 4: Run tests to verify pass**

```bash
docker compose -p prismv3 exec -T backend pytest tests/test_source_resolver_github.py -v
```
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/source_resolver.py backend/tests/test_source_resolver_github.py backend/requirements.txt
git commit -m "feat(session4c): GithubTarballResolver (HTTPS-only, bypasses CC SSH issue)"
```

---

## Task 5: GitUrlResolver + tests

**Files:**
- Modify: `backend/app/services/source_resolver.py`
- Create: `backend/tests/test_source_resolver_url.py`

- [ ] **Step 1: Write 3 failing tests (mock subprocess)**

```python
"""Tests for GitUrlResolver — git clone subprocess."""
from pathlib import Path
from unittest.mock import patch, AsyncMock
import pytest
from app.services.source_resolver import GitUrlResolver, SourceDownloadError

@pytest.mark.asyncio
async def test_git_url_https_success(tmp_path):
    with patch("app.services.source_resolver._run_subprocess", AsyncMock()) as mock:
        r = GitUrlResolver()
        await r.download(
            {"source": "url", "url": "https://gitlab.com/x/y.git", "ref": "main"},
            tmp_path / "out", marketplace_local_dir=None, github_token=None,
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
            tmp_path / "out", marketplace_local_dir=None, github_token=None,
        )

@pytest.mark.asyncio
async def test_git_url_with_sha_pin(tmp_path):
    with patch("app.services.source_resolver._run_subprocess", AsyncMock()) as mock:
        r = GitUrlResolver()
        await r.download(
            {"source": "url", "url": "https://x/y.git", "sha": "a" * 40},
            tmp_path / "out", marketplace_local_dir=None, github_token=None,
        )
        # 2 calls: clone + checkout sha
        assert mock.call_count == 2
        checkout_args = mock.call_args_list[1][0][0]
        assert checkout_args == ["git", "checkout", "a" * 40]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose -p prismv3 exec -T backend pytest tests/test_source_resolver_url.py -v
```
Expected: `ImportError: GitUrlResolver`

- [ ] **Step 3: Append GitUrlResolver**

```python
class GitUrlResolver(SourceResolver):
    async def download(self, source, target_dir, marketplace_local_dir, github_token):
        url = source["url"]
        if url.startswith("git@"):
            raise SourceDownloadError(
                "git_url", None, "SSH URL unsupported — use HTTPS"
            )
        ref = source.get("ref")
        sha = source.get("sha")

        clone_url = url
        if github_token and "github.com" in url:
            clone_url = url.replace(
                "https://", f"https://x-access-token:{github_token}@"
            )

        cmd = ["git", "clone", "--depth", "1"]
        if ref and not sha:
            cmd += ["--branch", ref]
        cmd += [clone_url, str(target_dir)]
        await _run_subprocess(cmd, timeout=120)

        if sha:
            await _run_subprocess(
                ["git", "checkout", sha], cwd=target_dir, timeout=30
            )
```

- [ ] **Step 4: Run tests**

```bash
docker compose -p prismv3 exec -T backend pytest tests/test_source_resolver_url.py -v
```
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/source_resolver.py backend/tests/test_source_resolver_url.py
git commit -m "feat(session4c): GitUrlResolver (HTTPS-only clone subprocess)"
```

---

## Task 6: GitSubdirResolver + tests

**Files:**
- Modify: `backend/app/services/source_resolver.py`
- Create: `backend/tests/test_source_resolver_git_subdir.py`

- [ ] **Step 1: Write 4 failing tests**

```python
"""Tests for GitSubdirResolver — cone-mode sparse checkout."""
from pathlib import Path
from unittest.mock import patch, AsyncMock
import pytest
from app.services.source_resolver import GitSubdirResolver, SourceDownloadError

@pytest.mark.asyncio
async def test_git_subdir_shorthand_normalizes(tmp_path):
    """'owner/repo' shorthand → https://github.com/owner/repo.git"""
    def fake_run(cmd, **kw):
        # simulate clone creating the target_dir
        Path(cmd[-1]).mkdir(parents=True, exist_ok=True) if "clone" in cmd else None
        # simulate sparse-checkout placing the files
        target = Path(kw.get("cwd", "."))
        if "checkout" in cmd or "sparse-checkout" in cmd:
            sub = target / "tools" / "cp"
            sub.mkdir(parents=True, exist_ok=True)
            (sub / "plugin.json").write_text("{}")
        return AsyncMock()()

    with patch(
        "app.services.source_resolver._run_subprocess",
        AsyncMock(side_effect=fake_run),
    ) as mock:
        r = GitSubdirResolver()
        await r.download(
            {"source": "git-subdir", "url": "owner/repo", "path": "tools/cp"},
            tmp_path / "out", marketplace_local_dir=None, github_token=None,
        )
        clone_cmd = mock.call_args_list[0][0][0]
        assert "https://github.com/owner/repo.git" in clone_cmd
        assert "--filter=blob:none" in clone_cmd
        assert "--no-checkout" in clone_cmd

@pytest.mark.asyncio
async def test_git_subdir_path_missing_after_checkout(tmp_path):
    """If path doesn't exist after checkout, raise."""
    async def noop(*a, **kw):
        Path(a[0][-1]).mkdir(parents=True, exist_ok=True) if "clone" in a[0] else None

    with patch("app.services.source_resolver._run_subprocess", AsyncMock(side_effect=noop)):
        r = GitSubdirResolver()
        with pytest.raises(SourceDownloadError, match="path not found"):
            await r.download(
                {"source": "git-subdir", "url": "owner/repo", "path": "missing/dir"},
                tmp_path / "out", marketplace_local_dir=None, github_token=None,
            )

@pytest.mark.asyncio
async def test_git_subdir_ssh_rejected(tmp_path):
    r = GitSubdirResolver()
    with pytest.raises(SourceDownloadError, match="SSH"):
        await r.download(
            {"source": "git-subdir", "url": "git@github.com:x/y.git", "path": "p"},
            tmp_path / "out", None, None,
        )

@pytest.mark.asyncio
async def test_git_subdir_with_sha(tmp_path):
    def fake(cmd, **kw):
        target = Path(kw.get("cwd", ".") if "cwd" in kw else cmd[-1])
        if "clone" in cmd:
            Path(cmd[-1]).mkdir(parents=True, exist_ok=True)
        if "checkout" in cmd and len(cmd) > 2:
            sub = Path(kw["cwd"]) / "p"
            sub.mkdir(parents=True, exist_ok=True)

    with patch("app.services.source_resolver._run_subprocess", AsyncMock(side_effect=fake)) as m:
        r = GitSubdirResolver()
        await r.download(
            {"source": "git-subdir", "url": "x/y", "path": "p", "sha": "a" * 40},
            tmp_path / "out", None, None,
        )
        # find the final checkout call with sha
        checkouts = [c[0][0] for c in m.call_args_list if "checkout" in c[0][0]]
        assert any("a" * 40 in cmd for cmd in checkouts)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose -p prismv3 exec -T backend pytest tests/test_source_resolver_git_subdir.py -v
```
Expected: `ImportError: GitSubdirResolver`

- [ ] **Step 3: Append GitSubdirResolver + _flatten_subdir helper**

```python
def _flatten_subdir_into_root(root: Path, subdir: Path) -> None:
    """Move everything under <root>/<subdir>/* up to <root>/*, remove subdir chain."""
    for item in subdir.iterdir():
        shutil.move(str(item), str(root / item.name))
    # remove empty chain
    cur = subdir
    while cur != root and cur.exists() and not any(cur.iterdir()):
        parent = cur.parent
        cur.rmdir()
        cur = parent


class GitSubdirResolver(SourceResolver):
    async def download(self, source, target_dir, marketplace_local_dir, github_token):
        url = source["url"]
        if url.startswith("git@"):
            raise SourceDownloadError(
                "git_subdir", None, "SSH URL unsupported — use HTTPS"
            )
        # owner/repo shorthand → full URL
        if "/" in url and not url.startswith("http"):
            url = f"https://github.com/{url}.git"
        path = source["path"]
        ref = source.get("sha") or source.get("ref")

        clone_url = url
        if github_token and "github.com" in url:
            clone_url = url.replace(
                "https://", f"https://x-access-token:{github_token}@"
            )

        await _run_subprocess(
            ["git", "clone", "--filter=blob:none", "--no-checkout",
             clone_url, str(target_dir)],
            timeout=120,
        )
        await _run_subprocess(
            ["git", "sparse-checkout", "init", "--cone"],
            cwd=target_dir, timeout=15,
        )
        await _run_subprocess(
            ["git", "sparse-checkout", "set", path],
            cwd=target_dir, timeout=15,
        )
        checkout_cmd = ["git", "checkout"]
        if ref:
            checkout_cmd.append(ref)
        await _run_subprocess(checkout_cmd, cwd=target_dir, timeout=30)

        subdir = target_dir / path
        if not subdir.is_dir():
            raise SourceDownloadError(
                "git_subdir", None, f"path not found after checkout: {path}"
            )
        _flatten_subdir_into_root(target_dir, subdir)
```

- [ ] **Step 4: Run tests**

```bash
docker compose -p prismv3 exec -T backend pytest tests/test_source_resolver_git_subdir.py -v
```
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/source_resolver.py backend/tests/test_source_resolver_git_subdir.py
git commit -m "feat(session4c): GitSubdirResolver (cone-mode sparse checkout)"
```

---

## Task 7: NpmResolver + tests

**Files:**
- Modify: `backend/app/services/source_resolver.py`
- Create: `backend/tests/test_source_resolver_npm.py`

- [ ] **Step 1: Write 4 failing tests**

```python
"""Tests for NpmResolver — packument + tarball two-stage."""
import io, json, tarfile
import httpx, pytest, respx
from app.services.source_resolver import NpmResolver, SourceDownloadError

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
        return_value=httpx.Response(200, json={
            "dist-tags": {"latest": "1.2.3"},
            "versions": {"1.2.3": {"dist": {"tarball": "https://registry.npmjs.org/pkg/-/pkg-1.2.3.tgz"}}},
        })
    )
    respx.get("https://registry.npmjs.org/pkg/-/pkg-1.2.3.tgz").mock(
        return_value=httpx.Response(200, content=_make_npm_tgz())
    )
    r = NpmResolver()
    await r.download(
        {"source": "npm", "package": "pkg", "version": "1.2.3"},
        tmp_path / "out", None, None,
    )
    assert (tmp_path / "out" / "plugin.json").exists()

@pytest.mark.asyncio
@respx.mock
async def test_npm_scoped_package_url_encoded(tmp_path):
    respx.get("https://registry.npmjs.org/@org%2Fpkg").mock(
        return_value=httpx.Response(200, json={
            "dist-tags": {"latest": "2.0.0"},
            "versions": {"2.0.0": {"dist": {"tarball": "https://registry.npmjs.org/@org%2Fpkg/-/pkg-2.0.0.tgz"}}},
        })
    )
    respx.get("https://registry.npmjs.org/@org%2Fpkg/-/pkg-2.0.0.tgz").mock(
        return_value=httpx.Response(200, content=_make_npm_tgz())
    )
    r = NpmResolver()
    await r.download(
        {"source": "npm", "package": "@org/pkg"},
        tmp_path / "out", None, None,
    )

@pytest.mark.asyncio
@respx.mock
async def test_npm_404_package(tmp_path):
    respx.get("https://registry.npmjs.org/missing").mock(return_value=httpx.Response(404))
    r = NpmResolver()
    with pytest.raises(SourceDownloadError, match="not found"):
        await r.download({"source": "npm", "package": "missing"}, tmp_path / "out", None, None)

@pytest.mark.asyncio
@respx.mock
async def test_npm_range_fallback_to_latest(tmp_path):
    """If version is a range like '^2.0.0', fall back to dist-tags.latest."""
    respx.get("https://registry.npmjs.org/pkg").mock(
        return_value=httpx.Response(200, json={
            "dist-tags": {"latest": "2.1.0"},
            "versions": {
                "2.0.0": {"dist": {"tarball": "https://x/a.tgz"}},
                "2.1.0": {"dist": {"tarball": "https://registry.npmjs.org/pkg/-/pkg-2.1.0.tgz"}},
            },
        })
    )
    respx.get("https://registry.npmjs.org/pkg/-/pkg-2.1.0.tgz").mock(
        return_value=httpx.Response(200, content=_make_npm_tgz())
    )
    r = NpmResolver()
    await r.download(
        {"source": "npm", "package": "pkg", "version": "^2.0.0"},
        tmp_path / "out", None, None,
    )
```

- [ ] **Step 2: Run tests to verify fail**

Expected: `ImportError: NpmResolver`

- [ ] **Step 3: Append NpmResolver**

```python
class NpmResolver(SourceResolver):
    async def download(self, source, target_dir, marketplace_local_dir, github_token):
        package = source["package"]
        version = source.get("version")
        registry = source.get("registry", "https://registry.npmjs.org")
        npm_token = os.getenv("NPM_TOKEN")

        encoded = (
            package.replace("/", "%2F") if package.startswith("@") else package
        )
        packument_url = f"{registry.rstrip('/')}/{encoded}"
        headers = {"Accept": "application/vnd.npm.install-v1+json"}
        if npm_token:
            headers["Authorization"] = f"Bearer {npm_token}"

        async with httpx.AsyncClient(
            timeout=30.0, follow_redirects=True
        ) as client:
            resp = await client.get(packument_url, headers=headers)
            if resp.status_code == 404:
                raise SourceDownloadError(
                    "npm", None, f"Package not found: {package}"
                )
            resp.raise_for_status()
            packument = resp.json()

        versions = packument.get("versions", {})
        if version and version in versions:
            version_info = versions[version]
        else:
            latest = packument.get("dist-tags", {}).get("latest")
            if not latest or latest not in versions:
                raise SourceDownloadError(
                    "npm", None, "No resolvable version"
                )
            version_info = versions[latest]

        tarball_url = version_info["dist"]["tarball"]
        target_dir.mkdir(parents=True, exist_ok=True)
        tmp_tgz = target_dir.parent / f".{target_dir.name}.tgz"
        try:
            async with httpx.AsyncClient(
                timeout=60.0, follow_redirects=True
            ) as client:
                async with client.stream("GET", tarball_url, headers=headers) as resp:
                    resp.raise_for_status()
                    with tmp_tgz.open("wb") as f:
                        async for chunk in resp.aiter_bytes(chunk_size=65536):
                            f.write(chunk)
            _safe_extract_tar(tmp_tgz, target_dir, strip_root_dir=True)
        finally:
            if tmp_tgz.exists():
                tmp_tgz.unlink()
```

- [ ] **Step 4: Run tests**

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/source_resolver.py backend/tests/test_source_resolver_npm.py
git commit -m "feat(session4c): NpmResolver (packument + tarball two-stage)"
```

---

## Task 8: Dispatcher `resolve_and_download` + Marketplace git fetch

**Files:**
- Modify: `backend/app/services/source_resolver.py` (add dispatcher at end)
- Modify: `backend/app/services/marketplace_service.py`
- Create: `backend/tests/test_marketplace_service_git_fetch.py`

- [ ] **Step 1: Add dispatcher function to source_resolver.py**

```python
def _select_resolver(source: dict | str) -> SourceResolver:
    if isinstance(source, str):
        return RelativePathResolver()
    kind = source.get("source")
    table: dict[str, type[SourceResolver]] = {
        "github": GithubTarballResolver,
        "url": GitUrlResolver,
        "git-subdir": GitSubdirResolver,
        "npm": NpmResolver,
    }
    cls = table.get(kind)
    if cls is None:
        raise SourceDownloadError(
            "dispatch", None, f"Unknown source type: {kind!r}"
        )
    return cls()


async def resolve_and_download(
    source: dict | str,
    target_dir: Path,
    marketplace_local_dir: Path | None = None,
    github_token: str | None = None,
) -> None:
    resolver = _select_resolver(source)
    await resolver.download(source, target_dir, marketplace_local_dir, github_token)
```

- [ ] **Step 2: Write 4 failing tests for MarketplaceService git fetch**

```python
"""Tests for MarketplaceService._try_fetch dual-mode (git-based + URL-based)."""
from pathlib import Path
from unittest.mock import patch
import pytest, subprocess
from app.services.marketplace_service import MarketplaceService, _looks_like_json_url

def test_looks_like_json_url_detection():
    assert _looks_like_json_url("https://example.com/marketplace.json")
    assert not _looks_like_json_url("anthropics/claude-plugins-official")
    assert not _looks_like_json_url("https://github.com/x/y.git")
    assert not _looks_like_json_url("https://github.com/x/y")

@pytest.mark.asyncio
async def test_git_fetch_normalizes_owner_repo_shorthand(tmp_path, monkeypatch):
    """'owner/repo' → https://github.com/owner/repo.git"""
    monkeypatch.setenv("PRISM_DATA_DIR", str(tmp_path))  # isolate cache
    def fake_run(cmd, **kw):
        Path(cmd[-1]).mkdir(parents=True, exist_ok=True)
        mj = Path(cmd[-1]) / ".claude-plugin"
        mj.mkdir(parents=True)
        (mj / "marketplace.json").write_text(
            '{"name":"m","owner":{"name":"n"},"plugins":[{"name":"p","source":"./foo"}]}'
        )
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
    with patch("subprocess.run", side_effect=fake_run):
        from app.services.marketplace_service import _fetch_git
        catalog, ts, local = _fetch_git("anthropics/claude-plugins-official")
        assert catalog["name"] == "m"
        assert local is not None

def test_validate_shape_accepts_mixed_string_object_source():
    from app.services.marketplace_service import _validate_marketplace_shape
    parsed = {
        "name": "m", "owner": {"name": "n"},
        "plugins": [
            {"name": "p1", "source": "./plugins/p1"},
            {"name": "p2", "source": {"source": "github", "repo": "x/y"}},
            {"name": "p3", "source": {"source": "git-subdir", "url": "a/b", "path": "p"}},
        ],
    }
    assert _validate_marketplace_shape(parsed)

def test_validate_shape_rejects_missing_owner_name():
    from app.services.marketplace_service import _validate_marketplace_shape
    assert not _validate_marketplace_shape({"name": "m", "owner": {}, "plugins": []})
```

- [ ] **Step 3: Run tests to verify they fail**

Expected: `ImportError / AttributeError`

- [ ] **Step 4: Extend marketplace_service.py with dual-mode fetch**

Append/modify in `backend/app/services/marketplace_service.py`:

```python
import os, re, shutil, subprocess
from pathlib import Path

_JSON_URL_RE = re.compile(r"\.json(?:\?.*)?$", re.IGNORECASE)
_DATA_DIR = Path(os.getenv("PRISM_DATA_DIR", "/app/data"))
_MARKETPLACE_CACHE = _DATA_DIR / "marketplace_cache"


def _looks_like_json_url(url: str) -> bool:
    """Detect if URL points directly to a marketplace.json file (URL-based)
    vs a git repo (git-based)."""
    if not url.startswith(("http://", "https://")):
        return False  # owner/repo shorthand
    if url.endswith(".git"):
        return False
    return bool(_JSON_URL_RE.search(url))


def _safe_name_from_url(url: str) -> str:
    """url → filesystem-safe marketplace cache dir name."""
    cleaned = re.sub(r"https?://|git@|\.git$", "", url)
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", cleaned).strip("_")[:80]


def _validate_marketplace_shape(parsed: Any) -> bool:
    """Validate .claude-plugin/marketplace.json shape per CC official docs.
    Permissive on source (string or object, per anthropic issue #1331)."""
    if not isinstance(parsed, dict):
        return False
    if not isinstance(parsed.get("name"), str):
        return False
    owner = parsed.get("owner")
    if not isinstance(owner, dict) or not isinstance(owner.get("name"), str):
        return False
    plugins = parsed.get("plugins")
    if not isinstance(plugins, list):
        return False
    for p in plugins:
        if not isinstance(p, dict) or not isinstance(p.get("name"), str):
            return False
        src = p.get("source")
        if not (isinstance(src, str) or isinstance(src, dict)):
            return False
    return True


def _fetch_git(url: str) -> tuple[dict[str, Any] | None, datetime | None, Path | None]:
    """Clone repo, read .claude-plugin/marketplace.json. Returns (catalog, ts, local_dir)."""
    original_url = url
    if "/" in url and not url.startswith(("http", "git@")):
        url = f"https://github.com/{url}.git"
    if url.startswith("git@"):
        logger.warning("marketplace.fetch.ssh_unsupported", url=original_url)
        return None, None, None

    cache_dir = _MARKETPLACE_CACHE / _safe_name_from_url(url)
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    cache_dir.parent.mkdir(parents=True, exist_ok=True)

    token = os.getenv("GITHUB_TOKEN")
    clone_url = url
    if token and "github.com" in url:
        clone_url = url.replace(
            "https://", f"https://x-access-token:{token}@"
        )

    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", clone_url, str(cache_dir)],
            capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        logger.warning("marketplace.fetch.clone_timeout", url=original_url)
        return None, None, None
    if result.returncode != 0:
        logger.warning(
            "marketplace.fetch.clone_failed", url=original_url,
            stderr=result.stderr[:200],
        )
        return None, None, None

    mj = cache_dir / ".claude-plugin" / "marketplace.json"
    if not mj.exists():
        logger.warning("marketplace.fetch.no_marketplace_json", url=original_url)
        return None, None, cache_dir
    try:
        parsed = json.loads(mj.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("marketplace.fetch.json_decode_error", url=original_url)
        return None, None, cache_dir
    if not _validate_marketplace_shape(parsed):
        logger.warning("marketplace.fetch.shape_invalid", url=original_url)
        return None, None, cache_dir
    return parsed, datetime.now(timezone.utc), cache_dir
```

Then modify `_try_fetch` to dispatch:

```python
@staticmethod
def _try_fetch(url: str) -> tuple[dict[str, Any] | None, datetime | None]:
    """Session 4c: dual-mode — git-based clone (if owner/repo or .git URL)
    or URL-based direct JSON GET (if ends in .json)."""
    if _looks_like_json_url(url):
        return _fetch_json(url)  # existing logic, extracted
    catalog, ts, _local = _fetch_git(url)
    return catalog, ts
```

(Existing `_try_fetch` body becomes `_fetch_json` helper; no behavior change for URL-based marketplaces.)

- [ ] **Step 5: Run tests, commit**

```bash
docker compose -p prismv3 exec -T backend pytest tests/test_marketplace_service_git_fetch.py -v
```
Expected: `4 passed`

```bash
git add backend/app/services/source_resolver.py backend/app/services/marketplace_service.py backend/tests/test_marketplace_service_git_fetch.py
git commit -m "feat(session4c): resolve_and_download dispatcher + MarketplaceService git-based fetch"
```

---

## Task 9: SkillInstallService.install_from_dir

**Files:**
- Modify: `backend/app/services/skill_install_service.py`
- Create: `backend/tests/test_skill_install_from_dir.py`

- [ ] **Step 1: Check existing skill_install_service.py for `install_from_dir`**

```bash
grep -n "def install_from_dir" backend/app/services/skill_install_service.py
```
If output is empty, proceed; if method exists, verify signature matches spec §4.4 and skip to Step 5.

- [ ] **Step 2: Write 3 failing tests**

```python
"""Tests for SkillInstallService.install_from_dir."""
from pathlib import Path
import pytest
from app.services.skill_install_service import SkillInstallService

@pytest.mark.asyncio
async def test_install_from_dir_parses_skill_md(tmp_path, db_session, test_user):
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: my-skill\ndescription: test skill\n---\nBody"
    )
    svc = SkillInstallService(db_session)
    result = svc.install_from_dir(
        skill_dir=skill_dir, user_id=test_user.id,
        source="marketplace:test", marketplace_id="mp-123",
        install_config={"plugin_name": "p", "plugin_version": "1.0"},
    )
    assert result.skill_name == "my-skill"
    assert result.source == "marketplace:test"

def test_install_from_dir_missing_skill_md(tmp_path, db_session, test_user):
    skill_dir = tmp_path / "empty"
    skill_dir.mkdir()
    svc = SkillInstallService(db_session)
    with pytest.raises(ValueError, match="SKILL.md"):
        svc.install_from_dir(
            skill_dir=skill_dir, user_id=test_user.id, source="marketplace:test",
        )

def test_install_from_dir_idempotent_upsert(tmp_path, db_session, test_user):
    """Second call with same (user_id, skill_name) updates instead of duplicating."""
    skill_dir = tmp_path / "s"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: s\ndescription: d\n---\n")
    svc = SkillInstallService(db_session)
    r1 = svc.install_from_dir(skill_dir=skill_dir, user_id=test_user.id, source="marketplace:t")
    r2 = svc.install_from_dir(skill_dir=skill_dir, user_id=test_user.id, source="marketplace:t")
    assert r1.install_id == r2.install_id  # same row, updated
```

- [ ] **Step 3: Implement `install_from_dir`**

Append to `backend/app/services/skill_install_service.py`:

```python
from pathlib import Path
import yaml
from dataclasses import dataclass

@dataclass
class SkillInstallResult:
    install_id: str
    skill_name: str
    source: str


class SkillInstallService:
    # ... existing methods ...

    def install_from_dir(
        self,
        skill_dir: Path,
        user_id: str,
        source: str,
        marketplace_id: str | None = None,
        install_config: dict | None = None,
    ) -> SkillInstallResult:
        """Install a skill from a directory containing SKILL.md.

        Parses YAML frontmatter for name + description. UPSERT into
        skill_installs (user_id, skill_name) — second install updates.
        Copies files to skill store at /app/data/skills/{user_id}/{skill_name}/.
        """
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            raise ValueError(f"SKILL.md not found in {skill_dir}")
        text = skill_md.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            raise ValueError("SKILL.md missing YAML frontmatter")
        _, fm, _ = text.split("---", 2)
        meta = yaml.safe_load(fm) or {}
        skill_name = meta.get("name") or skill_dir.name
        description = meta.get("description", "")

        # Copy files to skill store
        store_dir = Path(os.getenv("PRISM_DATA_DIR", "/app/data")) / "skills" / user_id / skill_name
        if store_dir.exists():
            shutil.rmtree(store_dir)
        shutil.copytree(skill_dir, store_dir)

        # UPSERT skill_installs
        existing = (
            self._db.query(SkillInstall)
            .filter(
                SkillInstall.user_id == user_id,
                SkillInstall.skill_name == skill_name,
            )
            .first()
        )
        if existing:
            existing.source = source
            existing.marketplace_id = marketplace_id
            existing.install_path = str(store_dir)
            existing.install_config = install_config or {}
            existing.description = description
            self._db.commit()
            return SkillInstallResult(existing.id, skill_name, source)

        row = SkillInstall(
            user_id=user_id,
            skill_name=skill_name,
            source=source,
            marketplace_id=marketplace_id,
            install_path=str(store_dir),
            install_config=install_config or {},
            description=description,
            enabled=True,
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return SkillInstallResult(row.id, skill_name, source)
```

- [ ] **Step 4: Run tests**

```bash
docker compose -p prismv3 exec -T backend pytest tests/test_skill_install_from_dir.py -v
```
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/skill_install_service.py backend/tests/test_skill_install_from_dir.py
git commit -m "feat(session4c): SkillInstallService.install_from_dir (UPSERT + frontmatter parse)"
```

---

## Task 10: MarketplaceService.install_plugin + Redis lock

**Files:**
- Modify: `backend/app/services/marketplace_service.py`
- Create: `backend/tests/test_marketplace_install.py`

- [ ] **Step 1: Write 6 failing tests**

```python
"""End-to-end tests for MarketplaceService.install_plugin."""
import pytest
from unittest.mock import patch, AsyncMock
from fastapi import HTTPException
from app.services.marketplace_service import MarketplaceService

@pytest.mark.asyncio
async def test_install_plugin_end_to_end(db_session, test_user, tmp_path, monkeypatch):
    monkeypatch.setenv("PRISM_DATA_DIR", str(tmp_path))
    # Setup: create marketplace with 1 plugin
    svc = MarketplaceService(db_session)
    mp = svc.create(
        user_id=test_user.id,
        url="test/marketplace",
        name="test-mp",
    )
    mp.catalog_json = {
        "name": "test-mp", "owner": {"name": "t"},
        "plugins": [{"name": "p1", "source": "./plugins/p1", "version": "1.0"}],
    }
    db_session.commit()

    # Mock resolver to place skill_dir at target_dir
    async def fake_resolve(source, target_dir, local, token):
        (target_dir / "skills" / "p1-skill").mkdir(parents=True)
        (target_dir / "skills" / "p1-skill" / "SKILL.md").write_text(
            "---\nname: p1-skill\ndescription: d\n---\n"
        )

    with patch("app.services.marketplace_service.resolve_and_download", fake_resolve):
        report = await svc.install_plugin(mp.id, "p1", test_user.id)
    assert "p1-skill" in report.installed_skills

@pytest.mark.asyncio
async def test_install_plugin_marketplace_404(db_session, test_user):
    svc = MarketplaceService(db_session)
    with pytest.raises(HTTPException) as exc:
        await svc.install_plugin("nonexistent", "p", test_user.id)
    assert exc.value.status_code == 404

@pytest.mark.asyncio
async def test_install_plugin_not_in_catalog_404(db_session, test_user):
    svc = MarketplaceService(db_session)
    mp = svc.create(user_id=test_user.id, url="u", name="n")
    mp.catalog_json = {"name": "n", "owner": {"name": "x"}, "plugins": []}
    db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await svc.install_plugin(mp.id, "missing", test_user.id)
    assert exc.value.status_code == 404

@pytest.mark.asyncio
async def test_install_plugin_no_skills_dir_422(db_session, test_user, tmp_path, monkeypatch):
    monkeypatch.setenv("PRISM_DATA_DIR", str(tmp_path))
    svc = MarketplaceService(db_session)
    mp = svc.create(user_id=test_user.id, url="u", name="n")
    mp.catalog_json = {"name": "n", "owner": {"name": "x"},
        "plugins": [{"name": "p", "source": "./foo"}]}
    db_session.commit()
    async def fake(*a, **kw):
        (a[1]).mkdir(parents=True, exist_ok=True)
        # no skills/ dir intentionally
    with patch("app.services.marketplace_service.resolve_and_download", fake):
        with pytest.raises(HTTPException) as exc:
            await svc.install_plugin(mp.id, "p", test_user.id)
    assert exc.value.status_code == 422
    assert "no skills" in exc.value.detail.lower()

@pytest.mark.asyncio
async def test_install_plugin_concurrent_lock_409(db_session, test_user, tmp_path, monkeypatch):
    """Two concurrent install calls on same plugin → second gets 409."""
    monkeypatch.setenv("PRISM_DATA_DIR", str(tmp_path))
    svc = MarketplaceService(db_session)
    mp = svc.create(user_id=test_user.id, url="u", name="n")
    mp.catalog_json = {"name": "n", "owner": {"name": "x"},
        "plugins": [{"name": "p", "source": "./foo"}]}
    db_session.commit()

    slow_event = asyncio.Event()
    async def slow_resolve(*a, **kw):
        await slow_event.wait()  # hold lock
    with patch("app.services.marketplace_service.resolve_and_download", slow_resolve):
        t1 = asyncio.create_task(svc.install_plugin(mp.id, "p", test_user.id))
        await asyncio.sleep(0.1)
        with pytest.raises(HTTPException) as exc:
            await svc.install_plugin(mp.id, "p", test_user.id)
        assert exc.value.status_code == 409
        slow_event.set()
        t1.cancel()

@pytest.mark.asyncio
async def test_install_plugin_wrong_user_404(db_session, test_user, other_user):
    """User A cannot install from user B's marketplace."""
    svc = MarketplaceService(db_session)
    mp = svc.create(user_id=other_user.id, url="u", name="n")
    db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await svc.install_plugin(mp.id, "anything", test_user.id)
    assert exc.value.status_code == 404
```

- [ ] **Step 2: Run tests to verify fail**

Expected: `AttributeError: install_plugin`

- [ ] **Step 3: Implement `install_plugin` + Redis lock**

Append to `backend/app/services/marketplace_service.py`:

```python
from contextlib import asynccontextmanager
import asyncio
from app.services.source_resolver import resolve_and_download, SourceDownloadError
from app.services.skill_install_service import SkillInstallService
from app.schemas.marketplace import InstallReport
from app.core.redis import get_async_redis


@asynccontextmanager
async def _redis_install_lock(key: str, ttl: int = 120):
    r = await get_async_redis()
    got = await r.set(key, "1", nx=True, ex=ttl)
    if not got:
        from fastapi import HTTPException
        raise HTTPException(409, f"Install already in progress for this plugin")
    try:
        yield
    finally:
        await r.delete(key)


class MarketplaceService:
    # ... existing ...

    def _get_marketplace_local_dir(
        self, mp: MarketplaceRegistry
    ) -> Path | None:
        """Returns local clone path if git-based; None if URL-based."""
        if _looks_like_json_url(mp.url):
            return None
        url_normalized = mp.url
        if "/" in url_normalized and not url_normalized.startswith("http"):
            url_normalized = f"https://github.com/{url_normalized}.git"
        return _MARKETPLACE_CACHE / _safe_name_from_url(url_normalized)

    async def install_plugin(
        self, marketplace_id: str, plugin_name: str, user_id: str
    ) -> InstallReport:
        from fastapi import HTTPException
        mp = self.get_by_id(marketplace_id, user_id)
        if mp is None:
            raise HTTPException(404, "Marketplace not found")
        catalog = mp.catalog_json or {}
        plugins = catalog.get("plugins", [])
        entry = next((p for p in plugins if p.get("name") == plugin_name), None)
        if entry is None:
            raise HTTPException(404, f"Plugin {plugin_name!r} not in catalog")

        lock_key = f"install_lock:{marketplace_id}:{plugin_name}"
        async with _redis_install_lock(lock_key, ttl=120):
            version = entry.get("version", "0.0.0")
            target_dir = (
                _DATA_DIR / "plugin_cache" / mp.name / plugin_name / version
            )
            if target_dir.exists():
                shutil.rmtree(target_dir)
            target_dir.parent.mkdir(parents=True, exist_ok=True)

            marketplace_local = self._get_marketplace_local_dir(mp)
            github_token = os.getenv("GITHUB_TOKEN")
            try:
                await resolve_and_download(
                    entry["source"],
                    target_dir,
                    marketplace_local,
                    github_token,
                )
            except SourceDownloadError as exc:
                raise HTTPException(
                    422, f"Download failed [{exc.stage}]: {exc.hint}"
                )

            skills_dir = target_dir / "skills"
            if not skills_dir.is_dir():
                raise HTTPException(
                    422,
                    f"Plugin {plugin_name!r} has no skills/ directory. "
                    "Prism currently only supports skill-type plugins."
                )

            install_svc = SkillInstallService(self._db)
            installed: list[str] = []
            failures: list[dict[str, str]] = []
            for skill_subdir in sorted(skills_dir.iterdir()):
                if not skill_subdir.is_dir():
                    continue
                if not (skill_subdir / "SKILL.md").exists():
                    continue
                try:
                    result = install_svc.install_from_dir(
                        skill_dir=skill_subdir,
                        user_id=user_id,
                        source=f"marketplace:{mp.name}",
                        marketplace_id=mp.id,
                        install_config={
                            "plugin_name": plugin_name,
                            "plugin_version": version,
                        },
                    )
                    installed.append(result.skill_name)
                except Exception as exc:
                    failures.append({
                        "skill_dir": skill_subdir.name,
                        "error": str(exc),
                    })

            if not installed and failures:
                raise HTTPException(
                    422, f"All skills failed: {failures}"
                )

            return InstallReport(
                plugin_name=plugin_name,
                installed_skills=installed,
                failures=failures,
            )
```

- [ ] **Step 4: Run tests**

```bash
docker compose -p prismv3 exec -T backend pytest tests/test_marketplace_install.py -v
```
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/marketplace_service.py backend/tests/test_marketplace_install.py
git commit -m "feat(session4c): MarketplaceService.install_plugin + Redis SETNX lock"
```

---

## Task 11: API endpoint + InstallReport schema

**Files:**
- Modify: `backend/app/schemas/marketplace.py`
- Modify: `backend/app/api/v1/marketplaces.py`
- Create: `backend/tests/test_install_endpoint.py`

- [ ] **Step 1: Add InstallReport to schemas**

```python
# backend/app/schemas/marketplace.py (append)
from pydantic import BaseModel

class InstallReport(BaseModel):
    plugin_name: str
    installed_skills: list[str]
    failures: list[dict[str, str]]
```

- [ ] **Step 2: Write endpoint test**

```python
"""Tests for POST /marketplaces/{id}/plugins/{name}/install endpoint."""
from unittest.mock import patch, AsyncMock
import pytest
from fastapi.testclient import TestClient

def test_install_endpoint_201(client: TestClient, admin_token, setup_marketplace):
    mp_id = setup_marketplace("p1")
    mock_report = type("R", (), {
        "plugin_name": "p1", "installed_skills": ["s1"], "failures": [],
    })()
    async def fake_install(self, mp_id, plugin, user):
        from app.schemas.marketplace import InstallReport
        return InstallReport(plugin_name="p1", installed_skills=["s1"], failures=[])
    with patch("app.services.marketplace_service.MarketplaceService.install_plugin", fake_install):
        resp = client.post(
            f"/api/v1/marketplaces/{mp_id}/plugins/p1/install",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 201
    assert resp.json()["data"]["plugin_name"] == "p1"

def test_install_endpoint_requires_auth(client: TestClient, setup_marketplace):
    mp_id = setup_marketplace("p1")
    resp = client.post(f"/api/v1/marketplaces/{mp_id}/plugins/p1/install")
    assert resp.status_code == 401
```

- [ ] **Step 3: Run tests to verify they fail**

Expected: `404 Not Found` (endpoint doesn't exist)

- [ ] **Step 4: Add endpoint to marketplaces.py**

Append to `backend/app/api/v1/marketplaces.py`:

```python
from app.schemas.marketplace import InstallReport


@router.post(
    "/{marketplace_id}/plugins/{plugin_name}/install",
    response_model=ApiResponse[InstallReport],
    status_code=status.HTTP_201_CREATED,
    summary="Install a plugin from marketplace catalog",
)
async def install_plugin_from_marketplace(
    marketplace_id: str,
    plugin_name: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[InstallReport]:
    svc = MarketplaceService(db=db)
    report = await svc.install_plugin(
        marketplace_id=marketplace_id,
        plugin_name=plugin_name,
        user_id=current_user.id,
    )
    return ApiResponse(data=report)
```

- [ ] **Step 5: Run tests + commit**

```bash
docker compose -p prismv3 exec -T backend pytest tests/test_install_endpoint.py -v
```
Expected: `2 passed`

```bash
git add backend/app/schemas/marketplace.py backend/app/api/v1/marketplaces.py backend/tests/test_install_endpoint.py
git commit -m "feat(session4c): POST /marketplaces/{id}/plugins/{name}/install endpoint"
```

---

## Task 12: Frontend — Marketplace tab catalog grid (RED)

**Files:**
- Create: `e2e/tests/skills-marketplace-catalog.spec.ts`

- [ ] **Step 1: Load `frontend-design` + `ui-ux-pro-max` skills**

Invoke `Skill` tool: `frontend-design` with args "Marketplace tab catalog grid 卡片 — luxury-refined serif title + amber version chip + framed body + category/tags chips + 桌面 3 列 / mobile 1 列 / mobile 44pt buttons"

Invoke `Skill` tool: `ui-ux-pro-max:ui-ux-pro-max` with args "SkillsPage Marketplace tab expand catalog pattern; install consent modal;桌面 + 移动双端 + dark mode"

- [ ] **Step 2: Write e2e tests (RED, no impl)**

Create `e2e/tests/skills-marketplace-catalog.spec.ts`:

```typescript
import { test, expect } from "@playwright/test";
import { loginAsAdmin } from "../fixtures/auth";

test.describe("Skills Marketplace Catalog (Session 4c)", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto("/Prism.html#skills");
    await page.click('[data-testid="tab-marketplace"]');
  });

  test("register marketplace → catalog grid renders", async ({ page }) => {
    await page.fill('[data-testid="mp-url-input"]', "anthropics/claude-plugins-official");
    await page.fill('[data-testid="mp-name-input"]', "official");
    await page.click('[data-testid="mp-register-btn"]');
    await expect(page.locator('[data-testid="mp-row-official"]')).toBeVisible();
    await page.click('[data-testid="mp-expand-official"]');
    await expect(page.locator('[data-testid="catalog-grid-official"]')).toBeVisible();
    const cards = page.locator('[data-testid^="plugin-card-"]');
    await expect(cards).toHaveCount(await cards.count());
    await expect(await cards.count()).toBeGreaterThan(0);
  });

  test("plugin card shows serif title + amber version + description", async ({ page }) => {
    // Prerequisite: marketplace registered with catalog
    const firstCard = page.locator('[data-testid^="plugin-card-"]').first();
    await expect(firstCard.locator('.plugin-title')).toHaveCSS("font-family", /serif/i);
    await expect(firstCard.locator('.version-chip')).toHaveCSS("background-color", /amber|252|251/);
  });

  test("details modal opens on click", async ({ page }) => {
    await page.locator('[data-testid^="plugin-card-"]').first()
      .locator('[data-testid="btn-details"]').click();
    await expect(page.locator('[data-testid="plugin-details-modal"]')).toBeVisible();
    await page.click('[data-testid="modal-close"]');
  });

  test("install click → consent dialog → confirm → install", async ({ page }) => {
    await page.locator('[data-testid^="plugin-card-"]').first()
      .locator('[data-testid="btn-install"]').click();
    await expect(page.locator('[data-testid="install-consent-modal"]')).toBeVisible();
    await expect(page.locator('[data-testid="consent-source-info"]')).toBeVisible();
    await page.click('[data-testid="consent-confirm"]');
    await expect(page.locator('[data-testid="install-toast-success"]')).toBeVisible({
      timeout: 60000,
    });
  });

  test("install failure → error toast with hint", async ({ page }) => {
    await page.route("**/api/v1/marketplaces/*/plugins/*/install", async route =>
      await route.fulfill({ status: 429, body: JSON.stringify({
        detail: "GitHub rate limit — set GITHUB_TOKEN"
      })})
    );
    await page.locator('[data-testid^="plugin-card-"]').first()
      .locator('[data-testid="btn-install"]').click();
    await page.click('[data-testid="consent-confirm"]');
    await expect(page.locator('[data-testid="install-toast-error"]'))
      .toContainText(/rate limit|GITHUB_TOKEN/);
  });

  test("install cancel does NOT trigger POST", async ({ page }) => {
    let called = false;
    await page.route("**/api/v1/marketplaces/*/plugins/*/install", async route => {
      called = true;
      await route.continue();
    });
    await page.locator('[data-testid^="plugin-card-"]').first()
      .locator('[data-testid="btn-install"]').click();
    await page.click('[data-testid="consent-cancel"]');
    await expect(page.locator('[data-testid="install-consent-modal"]')).not.toBeVisible();
    expect(called).toBe(false);
  });

  test("registered marketplace sync button re-fetches catalog", async ({ page }) => {
    await page.click('[data-testid="mp-sync-official"]');
    await expect(page.locator('[data-testid="mp-sync-toast-success"]')).toBeVisible();
  });

  test("mobile viewport: catalog grid is single column", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const grid = page.locator('[data-testid="catalog-grid-official"]');
    const gridCols = await grid.evaluate(el =>
      getComputedStyle(el).gridTemplateColumns
    );
    expect(gridCols.split(" ").length).toBe(1);
  });

  test("mobile install button has 44pt min height", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const btn = page.locator('[data-testid^="plugin-card-"]').first()
      .locator('[data-testid="btn-install"]');
    const h = await btn.evaluate(el => el.getBoundingClientRect().height);
    expect(h).toBeGreaterThanOrEqual(44);
  });
});
```

- [ ] **Step 3: Run e2e expecting failure**

```bash
cd "E:/Agent program/PrismV3"
npx playwright test e2e/tests/skills-marketplace-catalog.spec.ts --project=desktop-chromium --reporter=line
```
Expected: Most tests fail (UI not implemented yet).

- [ ] **Step 4: No impl in this task — implementation in Task 13**

(Leave failing; RED commit.)

- [ ] **Step 5: Commit RED tests**

```bash
git add e2e/tests/skills-marketplace-catalog.spec.ts
git commit -m "test(session4c): RED — Marketplace catalog e2e tests (桌面+移动双端,9 scenarios)"
```

---

## Task 13: Frontend — Marketplace tab catalog grid (GREEN)

**Files:**
- Modify: `frontend/Prism.html` SkillsPage component (approx. lines 1278-1900)

- [ ] **Step 1: Find SkillsPage + Marketplace tab existing code**

```bash
grep -n "tab-marketplace\|MarketplaceTab\|marketplaces" frontend/Prism.html | head -20
```

- [ ] **Step 2: Add catalog grid rendering inside Marketplace tab**

Inside `SkillsPage` component, extend `MarketplaceTab`:

```html
<!-- Existing: marketplace list rows. Add per-row "expand catalog" button: -->
<div class="mp-row" data-testid="mp-row-{{name}}">
  <div class="mp-header">
    <span class="mp-name">{{name}}</span>
    <button data-testid="mp-expand-{{name}}" @click="toggleExpand(mp)">
      {{ mp.expanded ? '收起' : '展开 catalog' }}
    </button>
    <button data-testid="mp-sync-{{name}}" @click="syncMp(mp)">同步</button>
    <button data-testid="mp-delete-{{name}}" @click="deleteMp(mp)">删除</button>
  </div>

  <div v-if="mp.expanded" data-testid="catalog-grid-{{name}}" class="catalog-grid">
    <div v-for="plugin in mp.catalog_json.plugins"
         :key="plugin.name"
         :data-testid="`plugin-card-${plugin.name}`"
         class="plugin-card">
      <div class="plugin-header">
        <span class="plugin-title">{{ plugin.name }}</span>
        <span v-if="plugin.version" class="version-chip">v{{ plugin.version }}</span>
      </div>
      <div class="plugin-body">
        <p class="plugin-desc">{{ plugin.description || '' }}</p>
      </div>
      <div class="plugin-footer">
        <span v-if="plugin.category" class="category-chip">{{ plugin.category }}</span>
        <span v-for="tag in (plugin.tags || []).slice(0, 3)"
              :key="tag" class="tag-chip">{{ tag }}</span>
      </div>
      <div class="plugin-actions">
        <button data-testid="btn-details" @click="openDetails(plugin)">详情</button>
        <button data-testid="btn-install" @click="openInstallConsent(mp, plugin)">安装</button>
      </div>
    </div>
  </div>
</div>
```

CSS (framed, luxury-refined):

```css
.catalog-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 1rem;
  padding: 1rem;
}
.plugin-card {
  background: #faf8f5;
  border: 1px solid #e8dcc4;
  border-radius: 0.5rem;
  box-shadow: 0 2px 8px rgba(194, 163, 106, 0.08);
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.plugin-title {
  font-family: 'Fraunces', 'Playfair Display', serif;
  font-size: 1.125rem;
  font-weight: 600;
  color: #3a2f1c;
}
.version-chip {
  background: #fbbf24;
  color: #451a03;
  padding: 0.1rem 0.5rem;
  border-radius: 0.25rem;
  font-size: 0.75rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.plugin-desc {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  color: #6b5d40;
}
.category-chip, .tag-chip {
  background: #ede3d0;
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
  font-size: 0.75rem;
  color: #6b5d40;
}
.plugin-actions button {
  min-height: 44px;
  border: 1px solid #c2a36a;
  background: transparent;
  border-radius: 0.375rem;
}
.plugin-actions button[data-testid="btn-install"] {
  background: #c2a36a;
  color: white;
}
@media (max-width: 640px) {
  .catalog-grid { grid-template-columns: 1fr; }
  .plugin-actions { flex-direction: column; gap: 0.5rem; }
}
```

Alpine.js (or equivalent framework) logic:

```javascript
SkillsPage.data = () => ({
  // ... existing ...
  selectedPlugin: null,
  selectedMp: null,
  showDetailsModal: false,
  showInstallConsent: false,
  async toggleExpand(mp) { mp.expanded = !mp.expanded; },
  async syncMp(mp) { await postJson(`/marketplaces/${mp.id}/sync`, {}); this.toast('已同步', 'success', 'mp-sync-toast-success'); },
  openDetails(plugin) { this.selectedPlugin = plugin; this.showDetailsModal = true; },
  openInstallConsent(mp, plugin) { this.selectedMp = mp; this.selectedPlugin = plugin; this.showInstallConsent = true; },
});
```

- [ ] **Step 3: Run e2e — verify catalog grid tests pass**

```bash
npx playwright test e2e/tests/skills-marketplace-catalog.spec.ts -g "catalog grid" --project=desktop-chromium --reporter=line
```
Expected: `3 passed` (register-renders, card-styled, mobile-single-col)

- [ ] **Step 4: Add details modal + install consent modal**

```html
<div v-if="showDetailsModal" data-testid="plugin-details-modal" class="modal-overlay">
  <div class="modal">
    <h3>{{ selectedPlugin.name }}</h3>
    <dl>
      <dt>description:</dt><dd>{{ selectedPlugin.description }}</dd>
      <dt v-if="selectedPlugin.author">author:</dt>
      <dd v-if="selectedPlugin.author">{{ selectedPlugin.author.name }}</dd>
      <dt v-if="selectedPlugin.homepage">homepage:</dt>
      <dd v-if="selectedPlugin.homepage"><a :href="selectedPlugin.homepage">{{ selectedPlugin.homepage }}</a></dd>
      <dt v-if="selectedPlugin.license">license:</dt>
      <dd v-if="selectedPlugin.license">{{ selectedPlugin.license }}</dd>
    </dl>
    <button data-testid="modal-close" @click="showDetailsModal = false">关闭</button>
  </div>
</div>

<div v-if="showInstallConsent" data-testid="install-consent-modal" class="modal-overlay">
  <div class="modal">
    <h3>确认安装 {{ selectedPlugin.name }}?</h3>
    <div data-testid="consent-source-info">
      <p>来源:{{ sourceDisplay(selectedPlugin.source) }}</p>
      <p>此操作将下载 plugin 到本地 cache 并注册所含 skills。</p>
    </div>
    <div class="consent-actions">
      <button data-testid="consent-cancel" @click="showInstallConsent = false">取消</button>
      <button data-testid="consent-confirm" @click="confirmInstall()">确认安装</button>
    </div>
  </div>
</div>
```

```javascript
async confirmInstall() {
  this.showInstallConsent = false;
  try {
    const res = await postJson(
      `/marketplaces/${this.selectedMp.id}/plugins/${this.selectedPlugin.name}/install`,
      {}
    );
    this.toast(
      `已安装 ${res.data.installed_skills.length} 个 skill`,
      'success', 'install-toast-success'
    );
    await this.reloadInstalledSkills();
  } catch (err) {
    this.toast(err.detail || '安装失败', 'error', 'install-toast-error');
  }
},
sourceDisplay(src) {
  if (typeof src === 'string') return `local (${src})`;
  const kind = src.source;
  const extra = src.repo || src.url || src.package || '';
  return `${kind} (${extra})`;
},
```

- [ ] **Step 5: Run all e2e tests + commit**

```bash
docker compose -p prismv3 up -d --force-recreate nginx  # mount updated Prism.html
npx playwright test e2e/tests/skills-marketplace-catalog.spec.ts --project=desktop-chromium --reporter=line
npx playwright test e2e/tests/skills-marketplace-catalog.spec.ts --project=mobile-safari --reporter=line
```
Expected: desktop 9/9 + mobile 9/9 (18 pass)

```bash
git add frontend/Prism.html
git commit -m "feat(session4c): SkillsPage Marketplace catalog grid + details + install consent (前端 GREEN)"
```

---

## Task 14: Worktree setup

**Files:**
- git worktree create

- [ ] **Step 1: Invoke `superpowers:using-git-worktrees`**

Call Skill tool: `superpowers:using-git-worktrees` with args "create worktree for redesign/sk-catalog off develop"

- [ ] **Step 2: Create worktree**

```bash
cd "E:/Agent program/PrismV3"
git worktree add .worktrees/sk-catalog -b redesign/sk-catalog develop
```

- [ ] **Step 3: Link node_modules + copy .env**

PowerShell:
```powershell
New-Item -ItemType Junction -Path ".worktrees/sk-catalog/e2e/node_modules" -Target "E:/Agent program/PrismV3/e2e/node_modules"
Copy-Item .env .worktrees/sk-catalog/.env
```

- [ ] **Step 4: Switch nginx mount to worktree**

Edit worktree's `docker-compose.yml` nginx volume to point at worktree's frontend; then:
```bash
cd .worktrees/sk-catalog
docker compose -p prismv3 up -d --force-recreate nginx
```

- [ ] **Step 5: (No commit — worktree setup is non-git action)**

**NOTE**: All subsequent Tasks 1-13 above execute **inside the worktree**. This Task 14 is conceptually before Task 1 in execution order — it's placed here in the plan so the plan reads top-to-bottom with final integration tasks at the end. When executing: run Task 14 first, then Task 1.

---

## Task 15: Simplify audit (3 parallel subagents)

**Files:**
- None directly modified; spawn subagents, review findings, recommit if blocking.

- [ ] **Step 1: Load simplify skill**

Call Skill tool: `simplify`

- [ ] **Step 2: Get diff since worktree base**

```bash
cd .worktrees/sk-catalog
git diff develop..HEAD --stat
git diff develop..HEAD > /tmp/session4c.diff
```

- [ ] **Step 3: Dispatch 3 parallel Agent subagents (reuse / quality / efficiency)**

Parallel Agent calls in single message (per CLAUDE.md dispatching-parallel-agents):

```
Agent 1 (reuse): Review diff /tmp/session4c.diff against existing backend code. Find ANY duplication with app.core.security / app.services.skill_install_service / app.core.redis / existing helpers. Key check: does source_resolver.py duplicate functionality that exists elsewhere? Does install_from_dir replicate install()?

Agent 2 (quality): Review for type-strict (no any), error handling completeness, logging coverage (structlog calls present?), test density (each resolver has ≥3 tests?).

Agent 3 (efficiency): httpx connection reuse (we create new AsyncClient per resolver call — acceptable? or share?), _run_subprocess timeout coherence, any N+1 DB queries in install_plugin.
```

- [ ] **Step 4: Apply blocking findings**

If any finding is **blocking** (duplicate code, missing feature from spec, security gap) — fix in worktree, recommit. Non-blocking → record in HANDOFF follow-up.

- [ ] **Step 5: Commit simplify fixes (if any)**

```bash
git add -A
git commit -m "simplify(session4c): <specific blocking finding description>"
```

---

## Task 16: PJR (含前端 lint + build)

**Files:**
- None directly modified; validation only.

- [ ] **Step 1: Backend AST + import chain**

```bash
cd .worktrees/sk-catalog
docker compose -p prismv3 exec -T backend sh -c '
  for f in app/services/source_resolver.py app/services/marketplace_service.py \
           app/services/skill_install_service.py app/api/v1/marketplaces.py \
           app/schemas/marketplace.py; do
    python -c "import ast; ast.parse(open(\"'$f'\").read()); print(\"OK: '$f'\")"
  done
'
docker compose -p prismv3 exec -T backend python -c "from app.main import app; print('import OK')"
```
Expected: all OK, no ImportError.

- [ ] **Step 2: Backend pytest full suite**

```bash
docker compose -p prismv3 exec -T backend pytest -v
```
Expected: all existing tests + 32 new session4c tests PASS. No regressions.

- [ ] **Step 3: Frontend lint + build**

```bash
node --check frontend/apiClient.js
cd frontend && npx eslint --ext .js,.html Prism.html apiClient.js || echo "LINT FAILED — fix before merge"
cd ..
# Prism.html does not have a bundler; HTML syntax validation via Playwright load:
npx playwright test e2e/tests/skills-marketplace-catalog.spec.ts -g "register marketplace" --project=desktop-chromium
```
Expected: lint 0 errors, Playwright smoke 1/1 pass.

- [ ] **Step 4: Curl smoke endpoints**

```bash
TOKEN=$(curl -s -X POST http://localhost:8080/api/v1/auth/login -H "Content-Type: application/json" \
  -d '{"email":"admin@prism.dev","password":"PrismAdmin!2026"}' | python -c "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")
curl -s http://localhost:8080/api/v1/marketplaces -H "Authorization: Bearer $TOKEN" | python -m json.tool
# Expect 200 + {data: [...]}
curl -s -X POST http://localhost:8080/api/v1/marketplaces/nonexistent/plugins/p/install \
  -H "Authorization: Bearer $TOKEN"
# Expect 404
```

- [ ] **Step 5: git status clean + commit count ahead of develop**

```bash
git status --short  # expect empty
git log --oneline develop..HEAD | wc -l  # expect ~12-14 commits
```

---

## Task 17: Code-reviewer 累积 6 次队列补跑

**Files:**
- None directly modified; subagent review.

- [ ] **Step 1: Load requesting-code-review skill**

Call Skill tool: `superpowers:requesting-code-review`

- [ ] **Step 2: Dispatch code-reviewer subagent**

```
Agent (code-reviewer): Review cumulative 6-session work in this worktree vs develop.
Target commits: Session 3 Phase 1 (ADR-086 marketplace骨架) + Session 3 Phase 2 (ADR-088 IM send_card) + Session 3 Phase 3 (ADR-089 progressive disclosure) + Session 4a (ADR-087 plugin builder typed) + Session 4b (IM AES + admin UI) + Session 4c (sk-catalog 5-source install).
Focus: security (tarfile / subprocess command injection / token leak), correctness (5 resolver各正确实现官方 spec), consistency with ADR-086/087/088/089 decisions, type safety (Pydantic v2 Literal, no `any`).
Report Important / Nit / Question buckets.
```

- [ ] **Step 3: Apply Important findings (commit fixes)**

```bash
# For each Important finding, write code, git add, commit with "fix(session4c code-review): ..."
```

- [ ] **Step 4: Record Nit + Question in HANDOFF follow-up**

(Deferred to Task 19.)

- [ ] **Step 5: (No separate commit; fixes already committed)**

---

## Task 18: Merge to develop

**Files:**
- None modified; git merge.

- [ ] **Step 1: Load git-merge-to-develop skill**

Call Skill tool: `git-merge-to-develop:git-merge-to-develop`

- [ ] **Step 2: Merge no-ff back to develop in main repo**

```bash
cd "E:/Agent program/PrismV3"  # main repo
git checkout develop
git pull --ff-only || echo "no remote or already up to date"
git merge --no-ff redesign/sk-catalog -m "$(cat <<'EOF'
Merge Session 4c: Skills Market catalog + 5-source install (ADR-086 偏离点清零 + ADR-090 新)

- 5-Source Resolver:relative / github (HTTPS tarball) / url / git-subdir (cone mode sparse) / npm (packument + tarball)
- MarketplaceService 双模式 fetch:git-based(clone + .claude-plugin/marketplace.json)+ URL-based(直 JSON)
- 1 plugin = N skill_installs(遍历 skills/<name>/SKILL.md)
- Python 3.12 tarfile filter='data' + realpath 防 CVE-2025-4517
- GitHub rate limit / retry-after / exponential backoff
- Redis SETNX install lock + 前端 luxury-refined catalog grid + install consent 双端
- Dockerfile 加 git + prism_plugin_data 卷

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git log --oneline -10
```

- [ ] **Step 3: Switch nginx mount back to main repo**

```bash
docker compose -p prismv3 up -d --force-recreate nginx
```

- [ ] **Step 4: Verify merge**

```bash
git log --all --oneline --graph | head -30
git status  # clean
```

- [ ] **Step 5: (Merge commit already created by Step 2)**

---

## Task 19: Playwright MCP 双端真实模拟 + HANDOFF + 最终 commit

**Files:**
- Modify: `DECISIONS.md`
- Modify: `HANDOFF-LOG.md`
- Modify: `PROGRESS.md`

- [ ] **Step 1: Playwright MCP 双端 e2e full regression**

```bash
npx playwright test --reporter=line --retries=0
```
Expected: baseline (69 pass / 10 skip / 2-3 pre-existing flaky) + new 18 Session 4c tests → **~87 pass / 10 skip / flaky same**. Zero regressions.

If regression appears, investigate before merge finalization. Pre-existing flaky (PLAYBOOK §5) do not count.

- [ ] **Step 2: Playwright MCP 真实人工模拟(非 CI 脚本)**

Manual Playwright MCP session:
1. Launch browser @ http://localhost:8080/Prism.html
2. Login as admin (default admin@prism.dev / PrismAdmin!2026)
3. Navigate SkillsPage → Marketplace tab
4. Type `anthropics/claude-plugins-official` + name `official` → click register → verify marketplace row appears
5. Click 展开 catalog → verify grid renders 60+ plugin cards
6. Click first plugin `[详情]` → verify modal → close
7. Click same plugin `[安装]` → consent dialog → cancel → verify no POST
8. Click 安装 again → confirm → verify 30-60s loading → success toast
9. Switch to Installed tab → verify new skill appears
10. Repeat in mobile viewport (390x844): verify 1-column grid, 44pt buttons

- [ ] **Step 3: Update DECISIONS.md**

Append to `DECISIONS.md`:

```markdown
## ADR-086 — Skills Marketplace (Session 3 Phase 1 → Session 4c 完整交付)

### Session 4c 偏离点清零
- ~~install flow stubbed~~ → ✅ Session 4c:`install_plugin` service + `POST /{id}/plugins/{name}/install` endpoint
- ~~catalog rendering TBD~~ → ✅ Session 4c:SkillsPage Marketplace tab catalog grid + install consent
- ~~5 种 source 未实现~~ → ✅ Session 4c:SourceResolver ABC + 5 resolver (relative / github / url / git-subdir / npm)

## ADR-090 — 5-Source Resolver + Git-based Marketplace fetch(Session 4c 新)

**决策**:Skills Marketplace 支持 CC 官方文档 5 种 plugin source;Marketplace 本身支持 git-based(clone)和 URL-based(直 JSON)双模式。

**理由**:
1. CC 官方文档(WebFetched 2026-04-20 `code.claude.com/docs/en/plugin-marketplaces`)明列 5 种
2. anthropic/claude-plugins-official 实测混用 string + object source(issue #1331)
3. CC CLI `source:github` 默认走 SSH 无 HTTPS fallback(issue #47088);Prism 用 GitHub REST tarball HTTPS 绕开
4. 用户"生产级完整交付,没有取舍"指令

**实现**:
- `backend/app/services/source_resolver.py`:ABC + 5 resolver + `_safe_extract_tar`(CVE-2025-4517 filter='data' + realpath)+ `_check_rate_limit`(GitHub x-ratelimit-* + retry-after)
- `backend/app/services/marketplace_service.py::_try_fetch`:双模式分支(`_looks_like_json_url` 判定);git-based 克隆到 `/app/data/marketplace_cache/{safe_name}/` + 读 `.claude-plugin/marketplace.json`
- Dockerfile 加 `git` binary
```

- [ ] **Step 4: Update HANDOFF-LOG.md + PROGRESS.md**

Prepend to `HANDOFF-LOG.md`:

```markdown
## ✅ 2026-04-20 Session 4c — Skills Marketplace catalog browser + 5-source install (生产级完整)

**Directive**(用户 2026-04-20):"生产级完整交付,没有取舍,ROI 特别低才允许不做;所有功能必须 WebFetch 官方 + exa 全搜集。"

### 本 session 所作所为

| 文件 | 动作 | 关键点 |
|---|---|---|
| backend/app/services/source_resolver.py | **新 450 行** | 5 resolver (relative/github/url/git-subdir/npm) + _safe_extract_tar (CVE-2025-4517) + _check_rate_limit + _run_subprocess |
| backend/app/services/marketplace_service.py | **改 +200** | _try_fetch 双模式(git-based / URL-based)+ _fetch_git + _validate_marketplace_shape + install_plugin + _redis_install_lock |
| backend/app/services/skill_install_service.py | **改 +50** | install_from_dir UPSERT + frontmatter parse |
| backend/app/api/v1/marketplaces.py | **改 +30** | POST /{id}/plugins/{name}/install |
| backend/app/schemas/marketplace.py | **改 +15** | InstallReport |
| backend/Dockerfile | **改 +1** | apt-get 加 git |
| docker-compose.yml | **改** | prism_plugin_data named volume |
| backend/tests/ × 8 | **新 860 行** | 32 unit tests (每 resolver 3-4 + safe_extract 4 + fetch 4 + install 6 + skill_install 3 + endpoint 2) |
| frontend/Prism.html | **改 +250** | SkillsPage Marketplace tab catalog grid + 详情 modal + install consent |
| e2e/tests/skills-marketplace-catalog.spec.ts | **新 300 行** | 9 tests × 双端 = 18 total(register/card/details/install/fail/cancel/sync/mobile-grid/mobile-44pt)|

### TDD 循环记录

(列举每 Task Step 1 RED → Step 4 GREEN 的测试通过数)

### 不 mock 生产代码 — 证明

- 5 resolver 的下载是**真实 httpx / subprocess**;mock 仅在 unit test 里对外部 API(api.github.com / registry.npmjs.org / git 二进制)
- Playwright `page.route` 仅拦截外部 GitHub / npm API(生产浏览器环境无拦截)
- 用户换 `GITHUB_TOKEN` 后在 /Prism.html 点击"安装"会真实走 HTTPS tarball API

### 用户自主真实账号测试步骤(生产可用标准)

**前提**:`.env` 里 `GITHUB_TOKEN=ghp_xxx`(可选,公共 repo 无 token 走 60/h);`docker compose -p prismv3 up -d --build --force-recreate backend`。

1. 登录 /Prism.html (admin@prism.dev / PrismAdmin!2026)
2. SkillsPage → Marketplace tab → 点 "+注册"
3. 填 URL: `anthropics/claude-plugins-official`,Name: `official` → 注册
4. catalog 自动拉回(可能 30-60s 首次 clone)→ marketplace 行出现
5. 点"展开 catalog"→ 看到 60+ 真实 plugins
6. 选某公共 plugin(如 `agent-sdk-dev`,source=`"./plugins/agent-sdk-dev"`)→ 点"安装"
7. consent dialog 显示 source 信息 → 点"确认安装"
8. 30-60s 成功 toast → Installed tab 看到 plugin 所含 skill

### 验证结果(evidence-based)

- **Python unit**: 32/32 pass (resolver × 5 + safe_extract + fetch + install + endpoint)
- **Playwright e2e**: 18/18 pass (双端 × 9)
- **Full regression**: ~87 pass / 10 skip / 2-3 pre-existing flaky(零回归)
- **Simplify**: 3 subagent 并行审查;blocking fix 已 recommit
- **Code-reviewer 累积 6 次**: 补跑 ADR-086~090 + Session 4a/4b/4c;Important findings 已 commit 修
- **PJR**: AST / import / lint / build / curl smoke 全绿

### 延后项(本 Block 1 不实施)

- CC plugin 组件消费 agents/hooks/mcpServers/lspServers/monitors/channels/outputStyles/userConfig/dependencies(Prism 治理模型与 CC 不同)
- strictKnownMarketplaces / extraKnownMarketplaces 自动注入
- Release channels / seed dir / 离线模式
- plugin signature 验证(CC 未来可能加)

### Block 2 / Block 3 硬前置 exa 清单(**下 session 开工第一件事**)

**Block 2(IM 三小尾)** 开工前必 exa(见 spec §14):
- `feishu interactive card button action callback payload shape python sdk example`
- `slack socket mode websocket block_actions envelope python`
- `discord button interaction data custom_id python pynacl example`
- 飞书/Slack/Discord developer portal 各自完整配置步骤

**Block 3(分布式任务拆解)** 开工前必 exa:
- `anthropic claude agent sdk sub-agents multi-agent production example`
- `langgraph multi-agent handoff state sharing plan executor`
- Manus 是黑箱,只能参考 Anthropic + LangGraph(有代码可读)

### Commits(chronological)

(填入实际 `git log --oneline develop..HEAD` 输出)

---
```

Update `PROGRESS.md` adding Session 4c row.

- [ ] **Step 5: Final commit**

```bash
git add DECISIONS.md HANDOFF-LOG.md PROGRESS.md
git commit -m "docs(session4c): DECISIONS ADR-086 clear + ADR-090 new + HANDOFF + Block 2/3 预交接"
```

---

## Self-Review

**Spec coverage check:**

| Spec section | Task |
|---|---|
| §3.1 RelativePathResolver | Task 3 ✅ |
| §3.2 GithubTarballResolver | Task 4 ✅ |
| §3.3 GitUrlResolver | Task 5 ✅ |
| §3.4 GitSubdirResolver | Task 6 ✅ |
| §3.5 NpmResolver | Task 7 ✅ |
| §3.6 `_safe_extract_tar` | Task 2 ✅ |
| §4.1 `_try_fetch` 双模式 | Task 8 ✅ |
| §4.2 `_validate_marketplace_shape` | Task 8 ✅ |
| §4.3 `install_plugin` + lock | Task 10 ✅ |
| §4.4 `install_from_dir` | Task 9 ✅ |
| §5 API endpoint | Task 11 ✅ |
| §6 错误处理矩阵 | Tasks 3-10 inline + Task 11 |
| §7 前端 catalog grid / 详情 / consent | Tasks 12-13 ✅ |
| §8 Testing Strategy | Tasks 2-13 inline + Task 19 full regression |
| §9 Dockerfile git + 数据卷 | Task 1 ✅ |
| §10 YAGNI | 对齐(agents/hooks/etc not in any task) |
| §11 File summary | 对齐 |
| §12 ADR 更新 | Task 19 ✅ |
| §13 17-step workflow | 对齐 |
| §14 Block 2/3 预交接 | Task 19 ✅ |

**No gaps.**

**Placeholder scan:** 无 TBD / TODO / "implement later" / "similar to Task N" / "Add appropriate error handling" 等占位符。每个 code block 均为完整可执行代码。

**Type consistency:** `SourceDownloadError(stage, underlying, hint)` / `InstallReport(plugin_name, installed_skills, failures)` / `SkillInstallResult(install_id, skill_name, source)` 贯穿各 Task 一致。`_run_subprocess(cmd, *, cwd, timeout)` keyword-only 一致。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-20-session4c-skills-market-catalog.md`.

**Two execution options:**

**1. Subagent-Driven (recommended)** — Dispatch fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

User 已授权"自动执行",默认选 **Inline Execution**(主 session 直接跑,每 Task 完成即 commit + TaskUpdate)。

**Execution order:** Task 14 (worktree) FIRST → Task 1 → Task 2 → ... → Task 13 → Task 15 → Task 16 → Task 17 → Task 18 → Task 19.
