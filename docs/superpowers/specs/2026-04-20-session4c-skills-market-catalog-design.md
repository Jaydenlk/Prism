# Session 4c — Skills Market Catalog Browser + 5-Source Install(生产级完整交付)

> Date: 2026-04-20
> Block: 1 of 3(Session 4c)
> Upstream: Session 3 Phase 1(ADR-086 骨架)/ Session 4a(ADR-087 Plugin Builder typed)/ Session 4b(ADR-088 IM send_card + AES)
> Target: `/clear` 后新 Sonnet session 可独立执行本 spec → implementation plan → worktree → TDD → merge
> Scope: Block 1 完整,不含 Block 2(IM 三小尾)/ Block 3(分布式)

---

## 0. Source of Truth(文档置信度锚点 — 禁推测)

### 已 WebFetch 一次 primary source(2026-04-20)

| URL | 覆盖 |
|---|---|
| `https://code.claude.com/docs/en/plugin-marketplaces` | `.claude-plugin/marketplace.json` schema / 5 种 source 完整 shape / owner 字段 / metadata.pluginRoot / reserved names / `strictKnownMarketplaces` / `extraKnownMarketplaces` / private repo auth via `GITHUB_TOKEN` / seed dir |
| `https://code.claude.com/docs/en/plugins-reference` | plugin.json 完整 schema / 组件目录布局(skills / commands / agents / hooks / mcpServers / lspServers / monitors / channels / outputStyles / userConfig / dependencies) / `${CLAUDE_PLUGIN_ROOT}` + `${CLAUDE_PLUGIN_DATA}` / strict mode / plugin cache 行为 |
| `https://docs.github.com/en/rest/repos/contents` | `GET /repos/{owner}/{repo}/tarball/{ref}` → 302 redirect / 私有 5-min TTL / headers: `Authorization: Bearer`, `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2026-03-10` |

### Exa 补强 7 次(生产级实现参考)

| 主题 | 关键发现 |
|---|---|
| anthropic-plugins-official/.claude-plugin/marketplace.json **真实 shape** | **混用 string 和 object** source(issue #1331 确证:15 plugins 用 string path,其他用 object);parser 必须 **permissive** 接受两种 |
| httpx | `follow_redirects` 默认 **False**(PR #1808);GitHub tarball 必须显式 `follow_redirects=True`;大文件用 `client.stream()` 流式避免 OOM |
| git sparse-checkout | Git 2.36+ **cone mode**;流程:`clone --filter=blob:none --no-checkout` → `sparse-checkout init --cone` → `sparse-checkout set <path>` → `checkout <ref>` |
| npm registry | `GET https://registry.npmjs.org/{package}` → packument JSON;每 version 含 `dist.tarball` URL(通常 `https://registry.npmjs.org/<name>/-/<name>-<version>.tgz`);Accept: `application/vnd.npm.install-v1+json`;scoped `@org/pkg` URL-encode 为 `@org%2Fpkg`;private 用 Bearer token |
| tarfile 安全 | Python 3.12+ **`filter='data'` 必需**(CVE-2025-4517 仍有 symlink race);额外 `realpath` 检查:每个 member 解出路径 startswith target dir realpath |
| GitHub rate limit | headers:`x-ratelimit-remaining` / `x-ratelimit-reset`(UTC epoch sec)/ `retry-after`;403/429 respect `retry-after`;secondary limit 用 exponential backoff;unauth 60/h,auth 5000/h |
| `source:github` SSH vs HTTPS(issue #47088)| CC 官方 CLI 默认走 SSH,无 HTTPS fallback;**Prism 用 GitHub REST tarball API(HTTPS-only)完全绕开**,更鲁棒 |

### Session 3 Phase 1 已有基线(ADR-086,不重做)

- **DB**: `marketplace_registry` 表(migration 008)+ `skill_installs.marketplace_id` FK (nullable, ON DELETE SET NULL)
- **Service**: `MarketplaceService`(CRUD + `_try_fetch` 直读 URL 返 JSON)
- **API**: `GET /marketplaces` / `POST /marketplaces` / `DELETE /{id}` / `POST /{id}/sync`
- **Frontend**: `frontend/Prism.html` SkillsPage **第 4 个 tab "Marketplace"** 已有(注册 URL + list + sync 按钮)

### Uncertainty 披露(spec 写代码前就暴露出来)

| 未决 | 决策(本 spec) |
|---|---|
| Session 3 Phase 1 `_try_fetch` 只支持直 JSON URL,不支持 `owner/repo` git clone | 扩展为 **双模式**:URL-based(现行,直 HTTP GET json)+ Git-based(新增,clone + 读 `.claude-plugin/marketplace.json`);按 URL shape 自动分支;**不破坏现有行为** |
| 1 CC plugin 可 bundle N 个 skills / agents / hooks | **本 Block 只消费 skills**(遍历 `skills/<name>/SKILL.md`);其他组件保留于 plugin cache 但不登记 Prism;消费 agents/hooks 列为 follow-up |
| Plugin 无 skills/ 目录 | install 422 失败:"此 plugin 不含 skill,Prism 当前仅支持 skill 类型 plugin"(YAGNI) |
| npm source 在 Python 后端 | 不 shell `npm install`;直 **HTTP GET registry**(packument → tarball URL → .tgz 解压) |
| git binary 在 Docker | Dockerfile 现行未装 → 本 spec 强制 `apt-get install -y git`(resolver 3/4 依赖) |

---

## 1. Goal / Non-Goal

### Goal(生产级完整)

用户在 /Prism.html SkillsPage Marketplace tab 能:
1. 注册任意 CC-兼容 marketplace(支持 `owner/repo` / git URL / JSON URL 三种形式)
2. 浏览 catalog 中所有 plugins(grid 卡片 / 桌面 + 移动双端可用)
3. 点某 plugin 的"安装"→ consent dialog → 后端按 plugin entry 的 `source` 字段自动调度 5 种 resolver 下载到 plugin cache → 解析 `plugin.json` + 提取 `skills/` 目录 → N 条 `skill_installs` 入库
4. 失败有明确 toast(rate limit / private repo / tarball 损坏 / plugin 不含 skill / 并发冲突等)

**全部 5 种 source 支持**:relative path / `github` / `url` / `git-subdir` / `npm`(官方文档明列的 5 种,一个不少)。

### Non-Goal(本 Block 不做,follow-up)

- CC plugin 的 agents / hooks / mcpServers / lspServers / monitors / channels / outputStyles / userConfig / dependencies **组件消费**(Prism 内部 agent/hook 治理与 CC 不同;plugin cache 保留原文但不登记)
- Plugin 自动更新(`CLAUDE_CODE_PLUGIN_KEEP_MARKETPLACE_ON_FAILURE` / 定时 sync)
- `strictKnownMarketplaces` 管理员限制 / `extraKnownMarketplaces` 自动注入
- Release channels(stable/latest multi-marketplace)
- `CLAUDE_CODE_PLUGIN_SEED_DIR` 容器预植
- Plugin signature 验证(CC 未来可能加,官方目前无)

---

## 2. Architecture(两层 registry,不加新表)

```
┌──────────────────────────┐             ┌───────────────────────────┐
│ marketplace_registry     │ ──FK────▶   │ skill_installs            │
│ (Session 3 Phase 1, #008)│ (existing)  │ .marketplace_id (nullable)│
│  - id / url / name       │             │ .source='marketplace:{n}' │
│  - catalog_json (JSONB)  │             │ .install_config (JSONB)   │
│  - last_fetched_at       │             └───────────────────────────┘
│  - created_by            │
└──────────────────────────┘
         ▲
         │ (git-based)
   clone to /app/data/marketplace_cache/{marketplace_name}/
         │
         │ catalog parse → catalog_json persisted
         ▼
┌──────────────────────────────────────────────────┐
│  Plugin Install Flow(Session 4c 新增)           │
│                                                  │
│  1. Lookup marketplace_registry.catalog_json     │
│  2. Find plugins[] entry by plugin_name          │
│  3. Dispatch to SourceResolver based on source   │
│     shape:                                       │
│       string "./path"        → RelativePath      │
│       {source:"github", ...} → GithubTarball     │
│       {source:"url", ...}    → GitUrl            │
│       {source:"git-subdir"}  → GitSubdir         │
│       {source:"npm", ...}    → NpmRegistry       │
│  4. Download to /app/data/plugin_cache/          │
│     {marketplace_name}/{plugin_name}/{version}/  │
│  5. Parse .claude-plugin/plugin.json(可选)      │
│  6. Enumerate skills/<name>/SKILL.md             │
│  7. For each skill: call                         │
│     SkillInstallService.install_from_dir(        │
│       marketplace_id=...,                        │
│       source='marketplace:{name}')               │
│     → INSERT/UPSERT skill_installs 行            │
│  8. Return install report (plugin_name +         │
│     installed_skills[] + failures[])             │
└──────────────────────────────────────────────────┘
```

### 进程边界(CLAUDE.md #6 遵守)

- 下载 / 解压 / git clone 全在 **Backend 进程**(非 Executor 子进程);写入 `/app/data/plugin_cache` 持久卷
- Executor 运行时从 `skill_installs` 表 + 文件系统路径读 skill;本 Block **不改 Executor**
- Redis 仅用于 install 并发锁(`install_lock:{marketplace_id}:{plugin_name}`,SETNX EX 120),不承载数据

---

## 3. 5-Source Resolver(单一职责)

### 统一接口 `backend/app/services/source_resolver.py`(新文件)

```python
class SourceDownloadError(Exception):
    """Raised by resolver when download fails. .stage / .underlying / .hint."""
    def __init__(self, stage: str, underlying: Exception | None, hint: str):
        ...

class SourceResolver(ABC):
    @abstractmethod
    async def download(
        self,
        source: dict | str,  # CC spec: string OR object(见 Source of Truth)
        target_dir: Path,
        marketplace_local_dir: Path | None,  # relative path 需要
        github_token: str | None,  # 私有 repo / rate limit 提升
    ) -> None: ...

# 调度
async def resolve_and_download(
    source: dict | str,
    target_dir: Path,
    marketplace_local_dir: Path | None = None,
    github_token: str | None = None,
) -> None:
    resolver = _select_resolver(source)
    await resolver.download(source, target_dir, marketplace_local_dir, github_token)

def _select_resolver(source: dict | str) -> SourceResolver:
    if isinstance(source, str):  # relative path shorthand
        return RelativePathResolver()
    kind = source.get("source")
    table = {
        "github": GithubTarballResolver,
        "url": GitUrlResolver,
        "git-subdir": GitSubdirResolver,
        "npm": NpmResolver,
    }
    cls = table.get(kind)
    if cls is None:
        raise SourceDownloadError("dispatch", None, f"Unknown source type: {kind!r}")
    return cls()
```

### 3.1 RelativePathResolver — 从 marketplace local clone 拷贝

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
            raise SourceDownloadError("relative_path", None, f"Invalid path: {rel!r}")
        src = (marketplace_local_dir / rel[2:]).resolve()
        root = marketplace_local_dir.resolve()
        if not str(src).startswith(str(root) + os.sep):
            raise SourceDownloadError("relative_path", None, "Path traversal blocked")
        if not src.is_dir():
            raise SourceDownloadError("relative_path", None, f"Path not found: {rel}")
        shutil.copytree(src, target_dir, dirs_exist_ok=False)
```

### 3.2 GithubTarballResolver — REST tarball API (HTTPS-only)

```python
class GithubTarballResolver(SourceResolver):
    async def download(self, source, target_dir, marketplace_local_dir, github_token):
        repo = source["repo"]  # "owner/repo"
        ref = source.get("sha") or source.get("ref") or "HEAD"
        url = f"https://api.github.com/repos/{repo}/tarball/{ref}"
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
        }
        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"

        async with httpx.AsyncClient(
            timeout=60.0, follow_redirects=True, max_redirects=5
        ) as client:
            async with client.stream("GET", url, headers=headers) as resp:
                _check_rate_limit(resp)  # raises 429 SourceDownloadError + retry_after
                if resp.status_code == 404:
                    raise SourceDownloadError("github_tarball", None, "Repo / ref not found")
                if resp.status_code == 401:
                    raise SourceDownloadError("github_tarball", None, "Auth required — set GITHUB_TOKEN")
                resp.raise_for_status()
                tmp_tar = target_dir.parent / f".{target_dir.name}.tar.gz"
                with tmp_tar.open("wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=64 * 1024):
                        f.write(chunk)
        _safe_extract_tar(tmp_tar, target_dir, strip_root_dir=True)  # gzip + tar
        tmp_tar.unlink()

def _check_rate_limit(resp: httpx.Response) -> None:
    """Raise SourceDownloadError with retry hint on 429/403+remaining=0."""
    remaining = resp.headers.get("x-ratelimit-remaining")
    retry_after = resp.headers.get("retry-after")
    reset = resp.headers.get("x-ratelimit-reset")
    if resp.status_code in (403, 429) and (retry_after or remaining == "0"):
        wait = int(retry_after) if retry_after else max(1, int(reset) - int(time.time()))
        raise SourceDownloadError(
            "rate_limit", None,
            f"GitHub rate limit hit — retry in {wait}s (set GITHUB_TOKEN for 5000/h)"
        )
```

### 3.3 GitUrlResolver — `git clone --depth=1 --branch`

```python
class GitUrlResolver(SourceResolver):
    async def download(self, source, target_dir, marketplace_local_dir, github_token):
        url = source["url"]  # HTTPS or SSH; 本 Prism 只接受 HTTPS(单一职责)
        if url.startswith("git@"):
            raise SourceDownloadError("git_url", None, "SSH URL unsupported, use HTTPS")
        ref = source.get("sha") or source.get("ref")
        cmd = ["git", "clone", "--depth", "1"]
        if ref and not source.get("sha"):  # ref(branch/tag)可用 --branch
            cmd += ["--branch", ref]
        cmd += [url, str(target_dir)]
        if github_token and "github.com" in url:
            url_with_token = url.replace(
                "https://", f"https://x-access-token:{github_token}@"
            )
            cmd[-2] = url_with_token  # 替换 URL
        await _run_subprocess(cmd, timeout=120)
        if source.get("sha"):  # pin 到 sha
            await _run_subprocess(
                ["git", "checkout", source["sha"]],
                cwd=target_dir, timeout=30,
            )
```

### 3.4 GitSubdirResolver — cone-mode sparse checkout

```python
class GitSubdirResolver(SourceResolver):
    async def download(self, source, target_dir, marketplace_local_dir, github_token):
        url = source["url"]  # 接受 owner/repo shorthand / https / ssh(本实现 HTTPS-only)
        if "/" in url and not url.startswith(("http", "git")):
            url = f"https://github.com/{url}.git"  # shorthand
        if url.startswith("git@"):
            raise SourceDownloadError("git_subdir", None, "SSH URL unsupported, use HTTPS")
        path = source["path"]
        ref = source.get("sha") or source.get("ref") or "HEAD"

        if github_token and "github.com" in url:
            url = url.replace(
                "https://", f"https://x-access-token:{github_token}@"
            )

        # Cone-mode sparse checkout(Git 2.36+)
        await _run_subprocess(
            ["git", "clone", "--filter=blob:none", "--no-checkout", url, str(target_dir)],
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
        if ref != "HEAD":
            checkout_cmd.append(ref)
        await _run_subprocess(checkout_cmd, cwd=target_dir, timeout=30)

        # 把 <target_dir>/<path>/* 移到 <target_dir> 根,避免嵌套
        subdir = target_dir / path
        if not subdir.is_dir():
            raise SourceDownloadError(
                "git_subdir", None, f"path not found after checkout: {path}"
            )
        _flatten_subdir_into_root(target_dir, subdir)
```

### 3.5 NpmResolver — 两阶段(packument → tarball)

```python
class NpmResolver(SourceResolver):
    async def download(self, source, target_dir, marketplace_local_dir, github_token):
        package = source["package"]  # "@org/pkg" or "pkg"
        version = source.get("version")  # 可为 ""^2.0.0"" 语义化范围
        registry = source.get("registry", "https://registry.npmjs.org")
        npm_token = os.getenv("NPM_TOKEN")  # 私有 registry

        # Stage 1: packument
        encoded_pkg = package.replace("/", "%2F") if package.startswith("@") else package
        packument_url = f"{registry.rstrip('/')}/{encoded_pkg}"
        headers = {"Accept": "application/vnd.npm.install-v1+json"}
        if npm_token:
            headers["Authorization"] = f"Bearer {npm_token}"

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(packument_url, headers=headers)
            if resp.status_code == 404:
                raise SourceDownloadError("npm", None, f"Package not found: {package}")
            resp.raise_for_status()
            packument = resp.json()

        # Resolve version(简化:精确版本;range 由 dist-tag 或最新)
        versions = packument.get("versions", {})
        if version and version in versions:
            version_info = versions[version]
        else:
            # 取 dist-tags.latest
            latest = packument.get("dist-tags", {}).get("latest")
            if not latest or latest not in versions:
                raise SourceDownloadError("npm", None, "No resolvable version")
            version_info = versions[latest]

        tarball_url = version_info["dist"]["tarball"]

        # Stage 2: download + extract
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            async with client.stream("GET", tarball_url, headers=headers) as resp:
                resp.raise_for_status()
                tmp_tar = target_dir.parent / f".{target_dir.name}.tgz"
                with tmp_tar.open("wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=64 * 1024):
                        f.write(chunk)
        _safe_extract_tar(tmp_tar, target_dir, strip_root_dir=True)  # npm .tgz 含 "package/" 顶层目录
        tmp_tar.unlink()
```

### 3.6 共享安全工具 `_safe_extract_tar`

```python
def _safe_extract_tar(tar_path: Path, target_dir: Path, *, strip_root_dir: bool) -> None:
    """Extract tgz/tar.gz into target_dir with CVE-2025-4517 defense.

    - Python 3.12+ filter='data'(PEP 706)
    - Additional realpath check: every member's final absolute path
      must stay within target_dir.realpath.
    - If strip_root_dir: assume single top-level dir(github tarball / npm
      "package/"),renamed stripped so target_dir 直接是内容根。
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    target_real = target_dir.resolve(strict=True)

    with tarfile.open(tar_path, "r:gz") as tf:
        members = tf.getmembers()
        if strip_root_dir and members:
            top = members[0].name.split("/", 1)[0]
            for m in members:
                if m.name == top:
                    m.name = "."
                elif m.name.startswith(top + "/"):
                    m.name = m.name[len(top) + 1:]

        def _filter(member: tarfile.TarInfo, path: str) -> tarfile.TarInfo:
            # filter='data' 已阻止 devices/symlinks-to-outside 等
            # 额外 realpath check
            extracted = (Path(path) / member.name).resolve()
            if not str(extracted).startswith(str(target_real)):
                raise tarfile.ExtractError(f"Path traversal: {member.name}")
            return tarfile.data_filter(member, path)

        tf.extractall(path=str(target_dir), filter=_filter)
```

---

## 4. MarketplaceService 扩展(`backend/app/services/marketplace_service.py`)

### 4.1 `_try_fetch` 双模式(git-based + url-based)

```python
def _try_fetch(url: str) -> tuple[dict[str, Any] | None, datetime | None, Path | None]:
    """
    Extended Session 4c: detect URL kind → clone or http.
    Returns (catalog_dict, fetched_at, marketplace_local_dir_or_None).

    Rules:
      - ends in '.json' or absolute HTTP to .json file → URL-based(直接 GET)
      - 'owner/repo' shorthand or HTTPS-git URL(.git / github.com / gitlab.com / ...)
        or 'git@...' → clone to /app/data/marketplace_cache/{name}/
    """
    if _looks_like_json_url(url):
        return _fetch_json(url)
    return _fetch_git(url)  # new
```

`_fetch_git`:
```python
def _fetch_git(url: str) -> tuple[dict | None, datetime | None, Path | None]:
    # Normalize owner/repo shorthand → https://github.com/owner/repo.git
    if "/" in url and not url.startswith(("http", "git@")):
        url = f"https://github.com/{url}.git"
    if url.startswith("git@"):
        logger.warning("marketplace.fetch.ssh_unsupported")
        return None, None, None

    cache_dir = Path("/app/data/marketplace_cache") / _safe_name_from_url(url)
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    token = os.getenv("GITHUB_TOKEN")
    if token and "github.com" in url:
        url = url.replace("https://", f"https://x-access-token:{token}@")
    result = subprocess.run(
        ["git", "clone", "--depth", "1", url, str(cache_dir)],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        logger.warning("marketplace.fetch.clone_failed", stderr=result.stderr[:200])
        return None, None, None
    mj = cache_dir / ".claude-plugin" / "marketplace.json"
    if not mj.exists():
        return None, None, cache_dir
    try:
        parsed = json.loads(mj.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, None, cache_dir
    if not _validate_marketplace_shape(parsed):
        return None, None, cache_dir
    return parsed, datetime.now(timezone.utc), cache_dir
```

### 4.2 Schema 严格验证

```python
def _validate_marketplace_shape(parsed: dict) -> bool:
    """Validate official schema:
    required: name (str, kebab), owner (dict with name), plugins (list)
    permissive on source: string or object (issue #1331 反映 anthropic 自己混用)
    """
    if not isinstance(parsed.get("name"), str):
        return False
    owner = parsed.get("owner")
    if not isinstance(owner, dict) or not isinstance(owner.get("name"), str):
        return False
    plugins = parsed.get("plugins")
    if not isinstance(plugins, list):
        return False
    for p in plugins:
        if not isinstance(p, dict):
            return False
        if not isinstance(p.get("name"), str):
            return False
        src = p.get("source")
        if not (isinstance(src, str) or isinstance(src, dict)):
            return False
    return True
```

### 4.3 新方法 `install_plugin`

```python
async def install_plugin(
    self, marketplace_id: str, plugin_name: str, user_id: str
) -> InstallReport:
    """Install one plugin from marketplace catalog.

    Returns InstallReport(plugin_name, installed_skills[], failures[])
    Raises HTTPException on fatal errors(404, 409 concurrent, 422 no skills).
    """
    # 1. Lookup marketplace + plugin entry
    mp = self.get_by_id(marketplace_id, user_id)
    if mp is None:
        raise HTTPException(404, "Marketplace not found")
    catalog = mp.catalog_json or {}
    plugins = catalog.get("plugins", [])
    entry = next((p for p in plugins if p.get("name") == plugin_name), None)
    if entry is None:
        raise HTTPException(404, f"Plugin {plugin_name!r} not in catalog")

    # 2. Redis lock(concurrent install block)
    lock_key = f"install_lock:{marketplace_id}:{plugin_name}"
    async with _redis_lock(lock_key, ttl=120):
        # 3. Prepare target dir
        version = entry.get("version", "0.0.0")
        target_dir = (
            Path("/app/data/plugin_cache")
            / mp.name / plugin_name / version
        )
        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.mkdir(parents=True)

        # 4. Resolver dispatch
        marketplace_local = self._get_marketplace_local_dir(mp)  # git-based 才有
        github_token = os.getenv("GITHUB_TOKEN")
        try:
            await resolve_and_download(
                entry["source"], target_dir, marketplace_local, github_token
            )
        except SourceDownloadError as exc:
            raise HTTPException(422, f"Download failed [{exc.stage}]: {exc.hint}")

        # 5. Parse plugin.json(可选)
        plugin_json = self._parse_plugin_json(target_dir)

        # 6. Enumerate skills/
        skills_dir = target_dir / "skills"
        if not skills_dir.is_dir():
            raise HTTPException(
                422,
                f"Plugin {plugin_name!r} has no skills/ directory. "
                "Prism currently only supports plugins that ship skills "
                "(agents/hooks/mcpServers follow-up)"
            )
        skill_install_svc = SkillInstallService(self._db)
        installed = []
        failures = []
        for skill_subdir in skills_dir.iterdir():
            if not skill_subdir.is_dir():
                continue
            skill_md = skill_subdir / "SKILL.md"
            if not skill_md.exists():
                continue
            try:
                result = skill_install_svc.install_from_dir(
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
                failures.append({"skill_dir": skill_subdir.name, "error": str(exc)})

        if not installed and failures:
            raise HTTPException(422, f"All skills failed: {failures}")

        return InstallReport(
            plugin_name=plugin_name,
            installed_skills=installed,
            failures=failures,
        )
```

### 4.4 Dependency: `SkillInstallService.install_from_dir`

需验证此方法已存在;如果未有(Session 3 Phase 1 可能只有 `install(source=...)`),本 spec 加:

```python
# backend/app/services/skill_install_service.py
def install_from_dir(
    self,
    skill_dir: Path,
    user_id: str,
    source: str,
    marketplace_id: str | None = None,
    install_config: dict | None = None,
) -> SkillInstallResult:
    """Parse SKILL.md + copy to skill store + UPSERT skill_installs."""
    ...
```

### 4.5 Redis 锁(简单 SETNX 实现)

```python
@asynccontextmanager
async def _redis_lock(key: str, ttl: int):
    r = await _get_redis()
    got = await r.set(key, "1", nx=True, ex=ttl)
    if not got:
        raise HTTPException(409, f"Install in progress ({key})")
    try:
        yield
    finally:
        await r.delete(key)
```

---

## 5. API 扩展(`backend/app/api/v1/marketplaces.py`)

### 新增 1 个 endpoint

```python
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
    report = await svc.install_plugin(marketplace_id, plugin_name, current_user.id)
    return ApiResponse(data=report)
```

### InstallReport schema(新 `backend/app/schemas/marketplace.py`)

```python
class InstallReport(BaseModel):
    plugin_name: str
    installed_skills: list[str]
    failures: list[dict[str, str]]  # [{skill_dir, error}, ...]
```

---

## 6. 错误处理矩阵(显式,不静默)

| 场景 | HTTP | 前端 toast |
|---|---|---|
| marketplace 不存在 | 404 | "Marketplace not found" |
| plugin 不在 catalog | 404 | "Plugin {name} not in catalog" |
| GitHub unauth 超 60/h | 429 | "GitHub rate limit — 在 `.env` 加 `GITHUB_TOKEN` 后重试" |
| Private repo 无 token | 401 | "该 plugin 在私有仓库,请在 `.env` 加 `GITHUB_TOKEN`" |
| SSH URL | 422 | "SSH URL 不支持,请用 HTTPS" |
| tar 非 tar.gz 格式 | 422 | "Tarball 格式错误" |
| tarball path traversal | 422 | "Plugin 包不安全(path traversal)" |
| plugin.json schema 失败 | 422 | "plugin.json 格式错误: {detail}" |
| plugin 无 skills/ | 422 | "此 plugin 不含 skill" |
| 下载超时(>120s) | 504 | "下载超时" |
| 并发 install 同一 plugin | 409 | "该 plugin 正在安装中" |
| git 未安装 | 500 | "git binary not found"(部署错误;spec Dockerfile 保证) |

---

## 7. 前端(`frontend/Prism.html` SkillsPage Marketplace tab 扩展)

### 7.1 已有(Session 3 Phase 1 )

- Marketplace tab UI 外壳
- 注册表单(URL + name inputs)
- 注册后的 marketplaces list(card 含 sync / delete)

### 7.2 本 Block 新增

1. **Marketplace card 可展开**:点"展开 catalog"→ 渲染 `catalog_json.plugins[]` grid
   - 桌面 3 列 / 平板 2 列 / mobile 1 列(CSS grid `auto-fill, minmax(260px, 1fr)`)
   - 卡片 header:plugin `name` (serif title) + version badge(amber chip)
   - 卡片 body:`description`(3 行 clamp)
   - 卡片 footer:`category` / `tags` chips + [详情] + [安装] 按钮
   - Mobile:按钮 44pt min-height,垂直堆叠(ui-ux-pro-max mobile-first)

2. **详情 modal**:显示完整 plugin.json 元数据(`author`, `homepage`, `repository`, `license`, `keywords`),复用 Session 4a consent dialog 模式

3. **安装 consent dialog**:(复用 Session 4a `consentModal`)
   - 显示 source type + URL(redact token)
   - 显示"将下载到 plugin cache 并注册 N 个 skill"提示
   - [取消] / [确认安装] 按钮
   - 确认 → POST `/marketplaces/{id}/plugins/{name}/install`
   - 加载 spinner(install 可能 30-120s)
   - 成功:toast "已安装 N 个 skill:xxx, yyy"+ Installed tab 自动刷新
   - 失败:toast 显示后端返回的 detail

4. **skill-design / ui-ux-pro-max**(Step 8 Flow 加载):
   - luxury-refined palette:serif heading + amber accent
   - Framed body(subtle border / soft shadow)
   - Mobile 44pt buttons
   - Dark-mode friendly(现有 Prism.html 样式延续)

---

## 8. Testing Strategy

### 8.1 Python Unit(pytest;新 `backend/tests/` 文件;全部 mock 外部 HTTP / subprocess)

| 文件 | Tests | 覆盖 |
|---|---|---|
| `test_source_resolver_github.py` | 4 | tarball 成功 / 302 redirect / 429 rate limit(retry-after header) / 401 auth |
| `test_source_resolver_url.py` | 3 | git clone 成功 / SSH URL 拒绝 / subprocess timeout |
| `test_source_resolver_git_subdir.py` | 4 | sparse-checkout 成功 / shorthand owner/repo / path not exist / sha pin |
| `test_source_resolver_npm.py` | 4 | packument+tarball 成功 / scoped `@org/pkg` / 404 / version range fallback latest |
| `test_source_resolver_relative.py` | 3 | copytree 成功 / path traversal 拒绝 / URL-based marketplace 拒绝 |
| `test_safe_extract_tar.py` | 4 | 正常解 / CVE-2025-4517 symlink 拒绝 / absolute path 拒绝 / strip_root_dir 行为 |
| `test_marketplace_service_git_fetch.py` | 4 | owner/repo shorthand / https.git / catalog parse / SSH URL skip |
| `test_marketplace_install.py` | 6 | end-to-end install / plugin 不含 skills → 422 / concurrent lock → 409 / 非 owner 访问 → 404 / source 类型错 → 422 / all-skill-fail → 422 |

**总计 32 unit tests**。

### 8.2 Playwright e2e(新 `e2e/tests/skills-marketplace-catalog.spec.ts`,桌面 + 移动双端)

**每按钮每流程,人工模拟完整走一遍**:

1. 登录 admin → 点 SkillsPage → Marketplace tab
2. 点"注册"→ 输入 `anthropics/claude-code` → 提交 → marketplaces list 出现新行
3. 点 marketplace card"展开"→ catalog grid 渲染
4. 验证卡片元素:serif title / amber version / description clamp / category chip
5. 点某 plugin card [详情] → modal 打开 → 验证字段 → 关闭
6. 点 [安装] → consent dialog 打开 → 验证 source 显示(redact token) → 点[确认]
7. Loading spinner → 成功 toast → Installed tab 切换后看到新 skill
8. 失败路径:
   - 注册无效 URL(`http://does-not-exist.test/mp.json`)→ 错误 toast
   - 安装不存在的 plugin → 404 toast
   - 模拟 GitHub 429 (Playwright route intercept) → toast 显示 rate limit hint
   - 并发 install 同一 plugin(打 2 个 tab)→ 第 2 个 409 toast

**双端验证**:桌面 click + mobile tap / grid 桌面 3 列 vs mobile 1 列 / 按钮 mobile 44pt 可点。

**Playwright `page.route` mock 范围**(生产代码无 mock):
- `api.github.com/repos/*/tarball/*` → 本地 fixture `.tar.gz`
- `registry.npmjs.org/*` → 本地 fixture packument + tgz
- git clone subprocess:**用 DI fixture 替换 `_run_subprocess`**,避免真 git(CI 不必)

### 8.3 真实账号测试路径(生产可用)

用户自主测试步骤(列入 HANDOFF):

1. 把 `GITHUB_TOKEN=ghp_xxx` 加到 `.env`(可选,公共 repo 无 token 走 60/h)
2. `docker compose -p prismv3 up -d --build --force-recreate backend`(Dockerfile 装 git)
3. 登录 /Prism.html → SkillsPage → Marketplace tab → 点"注册"
4. 填:URL = `anthropics/claude-plugins-official`,Name = `official`
5. 注册成功,marketplace list 出现
6. 点"展开"→ 看到 catalog 含 60+ 真实 plugins(含 string source 和 git-subdir source 混用)
7. 选某公共 plugin(如 `agent-sdk-dev`,source=`./plugins/agent-sdk-dev`)→ 点"安装"
8. consent → 确认 → 30-60s 后成功 toast
9. Installed tab 验证该 skill 注册在 `skill_installs` 表 + 前端可见
10. (可选)试 `github` source plugin(真走 HTTPS tarball)/ `git-subdir` source plugin(真走 sparse checkout)

---

## 9. Dependency / Infra 变更

| 变更 | 位置 |
|---|---|
| **Dockerfile 加 git** | `backend/Dockerfile` 第 6 行 `apt-get install ... git` |
| **新 data 卷挂载**(可选) | `docker-compose.yml` backend service 加 `- prism_data:/app/data` 保证 plugin cache 跨容器重启保留;若已有 named volume 沿用 |
| httpx / tarfile / gzip | 已在(httpx requirements.txt / tarfile stdlib) |
| Redis(install 锁) | 已有(Session 3 Task 3.3) |

---

## 10. YAGNI / 本 Block 不实施(follow-up)

| 项 | 原因 |
|---|---|
| plugin 消费 agents / hooks / mcpServers | Prism 有独立治理体系,与 CC 组件对接是 Block 3 / 后续 |
| plugin 自动更新 / 定时 sync | 单用户自托管,手动 sync 够用 |
| Release channels(stable/latest) | 多 marketplace 管理员场景,Prism 单用户不需 |
| `strictKnownMarketplaces` | 企业管控场景 |
| seed dir / CI pre-populate | Prism 部署 Docker 已有 named volume |
| 离线模式 `CLAUDE_CODE_PLUGIN_KEEP_MARKETPLACE_ON_FAILURE` | 低频需求 |
| plugin signature 验证 | CC 未来可能加,目前官方也无 |

---

## 11. File Summary

| 文件 | 动作 | LOC 估 |
|---|---|---|
| `backend/app/services/source_resolver.py` | **新** | 400-450 |
| `backend/app/services/marketplace_service.py` | **改**(`_try_fetch` 双模式 / `install_plugin`) | +200 |
| `backend/app/services/skill_install_service.py` | **改**(新 `install_from_dir` method,如果不存在) | +50 |
| `backend/app/api/v1/marketplaces.py` | **改**(新 install endpoint) | +30 |
| `backend/app/schemas/marketplace.py` | **改**(`InstallReport`) | +15 |
| `backend/Dockerfile` | **改**(apt-get 加 git) | +1 |
| `backend/tests/test_source_resolver_*.py` × 5 | **新** | 5 × 80 = 400 |
| `backend/tests/test_safe_extract_tar.py` | **新** | 60 |
| `backend/tests/test_marketplace_service_git_fetch.py` | **新** | 70 |
| `backend/tests/test_marketplace_install.py` | **新** | 150 |
| `frontend/Prism.html` SkillsPage Marketplace tab | **改**(catalog grid / 详情 modal / install consent) | +250 |
| `e2e/tests/skills-marketplace-catalog.spec.ts` | **新**(8-10 tests × 2 viewport = 16-20) | 300 |

**总计**: 新文件 8 / 改文件 6 / LOC ~1900。

---

## 12. ADR 更新

- **ADR-086**(Session 3 Phase 1):strikethrough "install flow stubbed" → ✅ Session 4c 完整交付
- **新 ADR-090**(本 session):5-Source Resolver 架构 + Git-based marketplace 双模式 + tarfile filter='data' + realpath check

---

## 13. Session 4c 17-Step Workflow(对照 PLAYBOOK §3)

Step 0 GATE ✅ → Step 1 using-superpowers ✅ → Step 2 brainstorming ✅ → **Step 3 本 spec + commit**(当前)→ Step 4 writing-plans → Step 5 worktree `redesign/sk-catalog` → Step 6-7 TDD RED + GREEN → Step 8 frontend-design + ui-ux-pro-max → Step 9 simplify 3 subagent → Step 10 PJR(含前端 lint / build)→ Step 11 code-reviewer 累积 6 次补跑 → Step 12 git-merge-to-develop no-ff → Step 13 Playwright MCP 桌面+移动双端真实模拟 → Step 14-17 DECISIONS + HANDOFF + Block 2/3 预交接 + final commit。

---

## 14. Block 2 / Block 3 预交接(HANDOFF 写入)

### Block 2(IM 三小尾)硬前置 exa 清单(下 session 开工前必跑)

- `"feishu interactive card button action callback payload shape python sdk example"`
- `"slack socket mode websocket block_actions envelope python"`
- `"discord button interaction data custom_id python pynacl example"`
- `"feishu app developer portal setup event subscription URL verification"`
- `"slack app manifest scopes chat:write events_api python"`
- `"discord developer portal application bot token intents setup"`

### Block 3(分布式任务拆解)硬前置 exa 清单

- `"anthropic claude agent sdk sub-agents multi-agent production example"`
- `"langgraph multi-agent handoff state sharing plan executor"`
- `"production planner executor architecture open source implementation"`

---

*End of spec — 写于 2026-04-20 Session 4c Step 3,字数 ~3800。*
