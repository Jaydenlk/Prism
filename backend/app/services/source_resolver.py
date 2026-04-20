"""SourceResolver — 5-strategy plugin source downloader (Session 4c).

Single-responsibility per resolver class. Each resolver fetches a CC plugin
package into a target directory per its source shape. See spec §3.

Source shapes (CC official docs, WebFetched 2026-04-20):
- string "./path"                          → RelativePathResolver
- {source:"github", repo, ref?, sha?}      → GithubTarballResolver
- {source:"url", url, ref?, sha?}          → GitUrlResolver
- {source:"git-subdir", url, path, ...}    → GitSubdirResolver
- {source:"npm", package, version?, ...}   → NpmResolver
"""
from __future__ import annotations

import asyncio
import os
import shutil
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

    Attributes:
        stage: which step failed (dispatch / github_tarball / git_url / ...)
        underlying: wrapped exception, if any
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
        source: dict[str, Any] | str,
        target_dir: Path,
        marketplace_local_dir: Path | None,
        github_token: str | None,
    ) -> None:
        """Download plugin source into target_dir.

        target_dir will exist (created by caller) but may be empty. On success,
        target_dir contains the plugin root (plugin.json etc. at top level).
        On failure, raise SourceDownloadError.
        """
        ...


def _safe_extract_tar(
    tar_path: Path, target_dir: Path, *, strip_root_dir: bool
) -> None:
    """Extract .tar.gz into target_dir with CVE-2025-4517 defense.

    Uses Python 3.12+ filter='data' (PEP 706) PLUS realpath check: every
    member's final absolute path MUST startswith target_dir.realpath().
    If strip_root_dir: the single top-level directory (e.g. GitHub tarball's
    "owner-repo-sha/" or npm's "package/") is flattened.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    target_real = str(target_dir.resolve())

    with tarfile.open(tar_path, "r:gz") as tf:
        members = tf.getmembers()
        if strip_root_dir and members:
            top = members[0].name.split("/", 1)[0]
            rewritten: list[tarfile.TarInfo] = []
            for m in members:
                if m.name == top or m.name == top + "/":
                    continue
                if m.name.startswith(top + "/"):
                    m.name = m.name[len(top) + 1 :]
                    rewritten.append(m)
                else:
                    rewritten.append(m)
            members = rewritten

        def _guard(member: tarfile.TarInfo, path: str) -> tarfile.TarInfo | None:
            filtered = tarfile.data_filter(member, path)
            if filtered is None:
                return None
            # Extra realpath defense beyond filter='data' (CVE-2025-4517).
            extracted = (Path(path) / filtered.name).resolve()
            if not str(extracted).startswith(target_real):
                raise tarfile.ExtractError(
                    f"Path traversal blocked: {member.name!r}"
                )
            return filtered

        for m in members:
            tf.extract(m, path=str(target_dir), filter=_guard)


async def _run_subprocess(
    cmd: list[str], *, cwd: Path | str | None = None, timeout: float = 60.0
) -> None:
    """Run subprocess async. Raise SourceDownloadError on non-zero / timeout."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd) if cwd else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise SourceDownloadError("binary_missing", exc, f"{cmd[0]} not found")
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise SourceDownloadError(
            "subprocess_timeout",
            None,
            f"Timed out after {timeout}s: {' '.join(cmd[:3])}...",
        )
    if proc.returncode != 0:
        raise SourceDownloadError(
            "subprocess_failed",
            None,
            f"{cmd[0]} exit {proc.returncode}: {stderr.decode()[:200]}",
        )


def _check_rate_limit(resp: httpx.Response) -> None:
    """Raise SourceDownloadError on GitHub rate limit 403/429."""
    if resp.status_code not in (403, 429):
        return
    remaining = resp.headers.get("x-ratelimit-remaining")
    retry_after = resp.headers.get("retry-after")
    reset = resp.headers.get("x-ratelimit-reset")
    if retry_after or remaining == "0":
        if retry_after:
            wait_s = int(retry_after)
        elif reset:
            wait_s = max(1, int(reset) - int(time.time()))
        else:
            wait_s = 60
        raise SourceDownloadError(
            "rate_limit",
            None,
            f"GitHub rate limit hit — retry in {wait_s}s "
            f"(set GITHUB_TOKEN for 5000/h instead of 60/h)",
        )
    if resp.status_code == 403:
        raise SourceDownloadError(
            "github_tarball",
            None,
            "403 forbidden (possibly abuse detection or missing scope) — "
            "verify GITHUB_TOKEN has repo scope",
        )


def _inject_github_token(url: str, token: str | None) -> str:
    """Rewrite github.com HTTPS URL to include x-access-token for private repos."""
    if not token or "github.com" not in url or not url.startswith("https://"):
        return url
    return url.replace("https://", f"https://x-access-token:{token}@", 1)


def _require_key(source: dict[str, Any], key: str, stage: str) -> Any:
    """Extract key from source dict or raise SourceDownloadError (not KeyError)."""
    value = source.get(key)
    if value is None:
        raise SourceDownloadError(
            stage, None, f"Missing required source field: {key!r}"
        )
    return value


async def _download_and_extract_tarball(
    url: str,
    headers: dict[str, str],
    target_dir: Path,
    *,
    stage: str,
    auth_error_hint: str = "Auth required",
    check_github_rate_limit: bool = False,
) -> None:
    """Shared tarball download+extract flow for github/npm resolvers.

    Streams to temp file adjacent to target_dir, _safe_extract_tar, cleanup.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    tmp_tar = target_dir.parent / f".{target_dir.name}.tar.gz"
    try:
        async with httpx.AsyncClient(
            timeout=60.0, follow_redirects=True, max_redirects=5
        ) as client:
            async with client.stream("GET", url, headers=headers) as resp:
                if resp.status_code == 404:
                    raise SourceDownloadError(
                        stage, None, f"Not found: {url}"
                    )
                if resp.status_code == 401:
                    raise SourceDownloadError(stage, None, auth_error_hint)
                if check_github_rate_limit:
                    _check_rate_limit(resp)
                resp.raise_for_status()
                with tmp_tar.open("wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=65536):
                        f.write(chunk)
        _safe_extract_tar(tmp_tar, target_dir, strip_root_dir=True)
    finally:
        if tmp_tar.exists():
            tmp_tar.unlink()


# =============================================================================
# Resolver 1/5 — Relative path (local copy from marketplace clone)
# =============================================================================


class RelativePathResolver(SourceResolver):
    async def download(
        self,
        source: dict[str, Any] | str,
        target_dir: Path,
        marketplace_local_dir: Path | None,
        github_token: str | None,
    ) -> None:
        if marketplace_local_dir is None:
            raise SourceDownloadError(
                "relative_path",
                None,
                "Relative-path source requires git-based marketplace (local "
                "clone). URL-based marketplaces don't support ./ paths "
                "(see CC docs).",
            )
        rel = source if isinstance(source, str) else source.get("path", "")
        if not rel.startswith("./") or ".." in rel:
            raise SourceDownloadError(
                "relative_path", None, f"Invalid path: {rel!r}"
            )
        src = (marketplace_local_dir / rel[2:]).resolve()
        root = marketplace_local_dir.resolve()
        if not str(src).startswith(str(root) + os.sep) and src != root:
            raise SourceDownloadError(
                "relative_path", None, "Path traversal blocked"
            )
        if not src.is_dir():
            raise SourceDownloadError(
                "relative_path", None, f"Path not found: {rel}"
            )
        shutil.copytree(src, target_dir, dirs_exist_ok=False)


# =============================================================================
# Resolver 2/5 — GitHub REST tarball API (HTTPS-only, bypasses CC SSH issue)
# =============================================================================


class GithubTarballResolver(SourceResolver):
    async def download(
        self,
        source: dict[str, Any] | str,
        target_dir: Path,
        marketplace_local_dir: Path | None,
        github_token: str | None,
    ) -> None:
        if not isinstance(source, dict):
            raise SourceDownloadError(
                "github_tarball", None, "github source must be object"
            )
        repo = _require_key(source, "repo", "github_tarball")
        ref = source.get("sha") or source.get("ref") or "HEAD"
        url = f"https://api.github.com/repos/{repo}/tarball/{ref}"
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
        }
        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"
        await _download_and_extract_tarball(
            url,
            headers,
            target_dir,
            stage="github_tarball",
            auth_error_hint="Auth required — set GITHUB_TOKEN for private repo",
            check_github_rate_limit=True,
        )


# =============================================================================
# Resolver 3/5 — Git URL (shallow clone HTTPS; SSH rejected)
# =============================================================================


class GitUrlResolver(SourceResolver):
    async def download(
        self,
        source: dict[str, Any] | str,
        target_dir: Path,
        marketplace_local_dir: Path | None,
        github_token: str | None,
    ) -> None:
        if not isinstance(source, dict):
            raise SourceDownloadError("git_url", None, "url source must be object")
        url = _require_key(source, "url", "git_url")
        if url.startswith("git@"):
            raise SourceDownloadError(
                "git_url", None, "SSH URL unsupported — use HTTPS"
            )
        ref = source.get("ref")
        sha = source.get("sha")

        clone_url = _inject_github_token(url, github_token)

        cmd = ["git", "clone", "--depth", "1"]
        if ref and not sha:
            cmd += ["--branch", ref]
        cmd += [clone_url, str(target_dir)]
        await _run_subprocess(cmd, timeout=120)

        if sha:
            await _run_subprocess(
                ["git", "checkout", sha], cwd=target_dir, timeout=30
            )


# =============================================================================
# Resolver 4/5 — Git subdirectory (cone-mode sparse checkout)
# =============================================================================


def _flatten_subdir_into_root(root: Path, subdir: Path) -> None:
    """Move all entries from <subdir> to <root>, then clean up subdir chain."""
    for item in list(subdir.iterdir()):
        dest = root / item.name
        if dest.exists():
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()
        shutil.move(str(item), str(dest))
    cur = subdir
    while cur != root and cur.exists() and not any(cur.iterdir()):
        parent = cur.parent
        cur.rmdir()
        cur = parent


class GitSubdirResolver(SourceResolver):
    async def download(
        self,
        source: dict[str, Any] | str,
        target_dir: Path,
        marketplace_local_dir: Path | None,
        github_token: str | None,
    ) -> None:
        if not isinstance(source, dict):
            raise SourceDownloadError(
                "git_subdir", None, "git-subdir source must be object"
            )
        url = _require_key(source, "url", "git_subdir")
        path = _require_key(source, "path", "git_subdir")
        if url.startswith("git@"):
            raise SourceDownloadError(
                "git_subdir", None, "SSH URL unsupported — use HTTPS"
            )
        # owner/repo shorthand → full URL
        if "/" in url and not url.startswith("http"):
            url = f"https://github.com/{url}.git"
        ref = source.get("sha") or source.get("ref")

        clone_url = _inject_github_token(url, github_token)

        await _run_subprocess(
            [
                "git",
                "clone",
                "--filter=blob:none",
                "--no-checkout",
                clone_url,
                str(target_dir),
            ],
            timeout=120,
        )
        await _run_subprocess(
            ["git", "sparse-checkout", "init", "--cone"],
            cwd=target_dir,
            timeout=15,
        )
        await _run_subprocess(
            ["git", "sparse-checkout", "set", path],
            cwd=target_dir,
            timeout=15,
        )
        checkout_cmd = ["git", "checkout"]
        if ref:
            checkout_cmd.append(ref)
        await _run_subprocess(checkout_cmd, cwd=target_dir, timeout=30)

        subdir = target_dir / path
        if not subdir.is_dir():
            raise SourceDownloadError(
                "git_subdir",
                None,
                f"path not found after checkout: {path}",
            )
        _flatten_subdir_into_root(target_dir, subdir)


# =============================================================================
# Resolver 5/5 — npm registry (packument → tarball two-stage)
# =============================================================================


class NpmResolver(SourceResolver):
    async def download(
        self,
        source: dict[str, Any] | str,
        target_dir: Path,
        marketplace_local_dir: Path | None,
        github_token: str | None,
    ) -> None:
        if not isinstance(source, dict):
            raise SourceDownloadError("npm", None, "npm source must be object")
        package = _require_key(source, "package", "npm")
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
        await _download_and_extract_tarball(
            tarball_url,
            headers,
            target_dir,
            stage="npm",
        )


# =============================================================================
# Dispatcher
# =============================================================================


def _select_resolver(source: dict[str, Any] | str) -> SourceResolver:
    """Select resolver by source shape. Strings → relative path;
    objects → dispatched on source['source']."""
    if isinstance(source, str):
        return RelativePathResolver()
    if not isinstance(source, dict):
        raise SourceDownloadError(
            "dispatch", None, f"source must be string or dict, got {type(source).__name__}"
        )
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
    source: dict[str, Any] | str,
    target_dir: Path,
    marketplace_local_dir: Path | None = None,
    github_token: str | None = None,
) -> None:
    """Entry point — dispatch to resolver and download."""
    resolver = _select_resolver(source)
    await resolver.download(source, target_dir, marketplace_local_dir, github_token)
