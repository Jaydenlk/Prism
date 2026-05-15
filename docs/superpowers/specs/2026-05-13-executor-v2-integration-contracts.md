# executor_v2 集成契约设计

> 补全审计暴露的设计缺失。每个契约定义：谁在什么时候做什么，数据格式是什么。

---

## 1. 生命周期顺序契约

```
__main__.py:
  parse_args → load_run_config → BackendCallback → HookRegistry
  → MemoryManager.recall(prompt) → 拿到记忆
  → PrismAgentRuntime(config, callback, registry, recalled_memories)
  → runtime.run():
      _build_options(recalled_memories)  ← 记忆注入到 system_prompt
      ClaudeSDKClient(options)
      client.connect()
      fire(SESSION_START)               ← 纯通知，不再修改 prompt
      client.query(prompt)
      receive_response loop
      fire(SESSION_END)                 ← 触发记忆提取
      client.disconnect()
```

**关键变更：记忆召回在 runtime 之前完成，作为参数传入。不再在 hook 里 mutate config。**

---

## 2. Hook Payload 类型契约

```python
class ToolPayload(TypedDict):
    tool_name: str
    tool_input: dict[str, Any]
    tool_use_id: str
    _event: str           # 事件名称，由 registry.fire() 自动注入

class ToolResultPayload(ToolPayload):
    tool_response: str
    _is_failure: bool     # 由 SDKBridge 根据事件类型设置

class SessionPayload(TypedDict):
    run_id: str
    session_id: str
    user_id: str
    model: str
    _event: str
```

**关键变更：**
- `registry.fire()` 自动注入 `_event` 到 payload
- `SDKBridge` 对 PostToolUseFailure 设置 `_is_failure=True`
- Safety handler 的 circuit breaker 因此能正常工作

---

## 3. 容错契约

| 组件 | 失败场景 | 处理策略 |
|---|---|---|
| Redis PUBLISH (text_delta) | 连接断、超时 | try/except → log warning → 跳过（不影响 run） |
| Redis SETEX (heartbeat) | 连接断 | 已有 try/except ✓ |
| HTTP callback | 5xx/网络 | 3 次退避重试 → DLQ ✓ |
| SDK subprocess | crash | SDK 抛异常 → run_error callback → 进程退出 |
| mem0 API | 超时/失败 | 已有 try/except → 返回空 ✓ |
| DB 查询 | 连接失败 | 进程退出 + ProcessManager 通知 run_error |

**关键变更：Redis PUBLISH 加 try/except。**

---

## 4. 安全契约

| 资源 | 访问控制 |
|---|---|
| Memory CRUD | user_id scope — delete 必须验证 memory 属于当前用户 |
| 工具执行 | PreToolUse hook 可拦截 — permission handler 从 config 读 blocked_tools |
| 路径访问 | PreToolUse（执行前）检查，不是 PostToolUse |
| API Key | 不出现在 log 中 — tool_input 做敏感字段 masking |

---

## 5. 类型契约

- HookHandler.callback 签名固定为 `Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]`
- 去掉 `Callable[..., ...]` 的 `...`
- runtime.py 中消息处理用 Union type 而非 `object`

---

## 6. 死代码清理

删除 5 个从未触发的事件常量：TURN_START, TURN_END, THINKING_DELTA, TOOL_START, TOOL_END。
保留 16 个实际使用的事件（10 SDK + 6 自定义）。
