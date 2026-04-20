# Blocker: marketplace_service._fetch_git 并发 rmtree

**发现者**: Session 4c code-reviewer(ADR-090 累积 6 次 review)
**发现日期**: 2026-04-20
**状态**: DEFERRED to future session(边界条件,需要跨 session 设计)
**Session 4c 选择**: 不修,记录在此,列入 HANDOFF follow-up

## 问题

`backend/app/services/marketplace_service.py::_fetch_git` 在 clone 前无条件 `shutil.rmtree(cache_dir)`:

```python
cache_dir = _MARKETPLACE_CACHE / _safe_name_from_url(url)
if cache_dir.exists():
    shutil.rmtree(cache_dir)  # ← 不安全
cache_dir.parent.mkdir(parents=True, exist_ok=True)
# ... git clone
```

如果同时有 `install_plugin` 请求正在从 `RelativePathResolver` 读 `cache_dir` 下的文件(`shutil.copytree(marketplace_local_dir / rel, target_dir)`),`_fetch_git` 的 rmtree 会把文件删掉,copytree FileNotFoundError。

## 触发条件(稀有)

- 单 admin 用户同时 sync marketplace + install 一个 relative-source plugin
- 多 admin 并发(Prism MVP 单用户自托管场景下低频)
- install_plugin 某 plugin 进行中(30-60s),另一线程调 sync (该 marketplace.id 上)

## 不修的理由(Session 4c 范围决策)

1. **设计复杂度**:正确修需要 Redis distributed read/write lock。`_fetch_git` 是 sync 方法,用 sync redis client 需要 extra 依赖。
2. **CLAUDE.md "禁止打补丁"**: Session 3 Phase 1 的 `_fetch_git` 行为是"best-effort fetch,失败不 fail registration"。加 lock 要改这个契约。
3. **低发生率**: single-user self-hosted + sync 是稀有操作(admin 手动点击),install 持续 30-60s。碰撞窗口小。
4. **不会数据损坏**: install_plugin 最坏情况 422 "Path not found",再 retry 即成功。Redis 锁 + retry 在客户端层也能解。

## 下个 session 修复建议

两种方案:

### A. Redis 读/写锁(生产级)

- `sync()` acquire **exclusive write lock** `mp_lock:{id}` via Redlock 或 Lua SETNX
- `install_plugin()` acquire **shared read lock** via counter pattern
- `_fetch_git` 只在写锁下 rmtree

### B. FS-level lock(简化)

- 使用 `fcntl.flock`(Linux)/ portalocker(跨平台)给 `cache_dir` 加文件锁
- `_fetch_git` acquire exclusive;`RelativePathResolver` acquire shared
- 单机场景足够(Prism MVP)

### C. "Copy-on-install" 策略(最简)

- install_plugin 从 `marketplace_cache/{mp}/` 用 `shutil.copytree` 到 `plugin_cache/{tmp}/` 前,先 *fully copy whole subtree* 再操作。
- 如果 sync 在 copy 进行中 rmtree,copytree 会部分成功。
- 简化但依赖 OS 文件系统语义。

推荐 B(最小改动,Prism 单机 self-hosted 已满足)。

## 验证步骤(修完之后)

单测:
```python
async def test_fetch_git_blocks_during_install(tmp_path):
    # mock install_plugin holding cache_dir
    # call _fetch_git → expect to wait / fail with "busy"
```

端到端:
- Playwright:opens 2 tabs;tab1 点 install 某 plugin;tab2 立即点 sync marketplace
- Expect:tab2 sync 返回 409 或等待 tab1 完成

## 链接到 ADR-090 偏离点

DECISIONS.md ADR-090 条目下加:
> **偏离点(deferred)**: concurrent _fetch_git rmtree vs install_plugin copytree 竞态 — 需 Redis 或 FS 锁 future fix。详见 docs/superpowers/blockers/2026-04-20-marketplace-concurrent-rmtree.md
