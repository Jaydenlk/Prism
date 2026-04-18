# Prism v2 PRD v4 — Claude Code 移交改写指令

> **定位**: 给 Claude Code(1M context)的完整改写指令,用于完成 DOC-03~12 + DOC-CC-ONBOARDING 的改写
> **前置完成**: DOC-00 v4 / DOC-01 v4 / DOC-02 v4 三份已在 Claude Web 完成
> **核心原则**: **改不是重写** — 99% 照搬原文,只在 review 发现的具体位置精确修补,保留目录/章节编号/Part A/B 格式/ADR 编号
> **总任务量**: 10 份文档改写 + 1 份先导文档新建
> **日期**: 2026-04-18

---

## 目录

1. [执行前准备](#1-执行前准备)
2. [改写 SOP(标准操作流程)](#2-改写-sop标准操作流程)
3. [跨文档全局修订点(所有文档都要遵守)](#3-跨文档全局修订点)
4. [DOC-03 改写指令(Agent Runtime & Harness Core)](#4-doc-03-改写指令)
5. [DOC-04 改写指令(Agent Orchestration)](#5-doc-04-改写指令)
6. [DOC-05 改写指令(Plugin Ecosystem)](#6-doc-05-改写指令)
7. [DOC-06 改写指令(Backend Auth & User)](#7-doc-06-改写指令)
8. [DOC-07 改写指令(Backend Session-Run-Task)](#8-doc-07-改写指令)
9. [DOC-08 改写指令(Backend IM Gateway)](#9-doc-08-改写指令)
10. [DOC-09 改写指令(Backend MCP-Provider-Admin)](#10-doc-09-改写指令)
11. [DOC-10 改写指令(Frontend Foundation)](#11-doc-10-改写指令)
12. [DOC-11 改写指令(Frontend Features)](#12-doc-11-改写指令)
13. [DOC-12 改写指令(Observability & Entropy)](#13-doc-12-改写指令)
14. [DOC-CC-ONBOARDING 新建指令](#14-doc-cc-onboarding-新建指令)
15. [完工交付清单](#15-完工交付清单)

---

## 1. 执行前准备

### 1.1 必读输入文件

Claude Code 开工前必须读完以下所有文件:

| 类别 | 文件 | 作用 |
|---|---|---|
| **上游参考 v4 完成品** | `DOC-00-v4.md` | 愿景+原则,所有后续 DOC 的根 |
| | `DOC-01-v4.md` | 系统架构,Schema 真相源(19 张表) |
| | `DOC-02-v4.md` | Model Adapter + Prompt Engine,Task 格式模板 |
| **v3 原文(待改写)** | `DOC-03-Agent-Runtime-and-Harness-Core.md` | 80KB,6 Task |
| | `DOC-04-Agent-Orchestration.md` | 56KB,4 Task |
| | `DOC-05-Plugin-Ecosystem.md` | 63KB,5 Task |
| | `DOC-06-Backend-Auth-and-User.md` | 27KB,2 Task |
| | `DOC-07-Backend-Session-Run-Task.md` | 48KB,4 Task |
| | `DOC-08-Backend-IM-Gateway.md` | 24KB,3 Task |
| | `DOC-09-Backend-MCP-Provider-Admin.md` | 17KB,2-3 Task |
| | `DOC-10-Frontend-Foundation.md` | 9KB,3 Task |
| | `DOC-11-Frontend-Features.md` | 25KB,5 Task |
| | `DOC-12-Observability-and-Entropy.md` | 27KB,3 Task(要扩到 7 Task) |
| **Review 输入** | `review-master.md` | **最重要**,跨 Batch 总纲 + 115 修改点 + P0/P1/P2 分级 |
| | `review-batch1-v2.md` | DOC-00/01/02 层 review |
| | `review-batch2.md` | DOC-03/04/05 层 review(45KB,最大) |
| | `review-batch3.md` | DOC-06/07/08/09 层 review |
| | `review-batch4.md` | DOC-10/11 层 review |
| | `review-batch5.md` | DOC-12 层 review |
| | `review-patch-pdf.md` | CC PDF 10 个补丁点(P1-P10) |
| | `user-preferences-archive.md` | 用户 14 条硬要求 |
| **已完成 v4 参考** | 上面三份 v4 | 改写密度和风格的标杆 |

### 1.2 硬铁律(开工前记牢)

**这些规则在所有改写工作中不可违反**:

1. **改不是重写**:99% 照搬原文,只在 review 发现的具体位置精确修补
2. **保留结构**:目录、章节编号、Task 编号、Part A/B 格式、ADR 编号全部保留
3. **保留已有决策**:架构方向、技术栈、Schema 骨架、Task 拆分不动
4. **扩充,不删除**:v3.1 新增的 Task 全部保留(DOC-03 Task 3.6 / DOC-04 Task 4.5 / DOC-05 Task 5.5-5.7 / DOC-09 Task 9.3 / DOC-11 Task 11.5 都要保留),只修改它们的做法
5. **密度达标**:Sonnet 4.6 看完能零猜测地开写,不留 `...` 省略 / `TODO` 占位
6. **Part A 必含 6 节**:问题陈述 / 设计决策(ADR) / CC 架构映射 / 数据模型 / Harness 交互 / 验收标准
7. **Part B 必含 7 节**:上下文 / Skill 加载 / 前置条件 / 文件树 / 实现规范(精确到函数签名) / 验证步骤(含期望输出) / 完成后
8. **每个 Part A 结尾加 ADR 编号**,引用 DOC 全局 ADR 编号空间(DOC-02 已用到 ADR-017,DOC-03 从 ADR-020 开始接续)
9. **每份改完后加附录 A**:v4 修订清单表格,列出每处修订的位置、内容、来源 review

### 1.3 输出文件命名

- 改后文件命名为 `DOC-XX-v4.md`,与 v3 原文同目录
- 新建 `DOC-CC-ONBOARDING.md`(无 v4 后缀,它是全新的)
- 保留 v3 原文不动(作为审计和 diff 参照)

---

## 2. 改写 SOP(标准操作流程)

每份 PRD 按以下 6 步执行:

### Step 1 — 读取原文和 review

```bash
# 读原文
read /mnt/project/DOC-XX-...md

# 对照 review 找出该 DOC 的所有问题点
grep -A 20 "DOC-XX" review-batchN.md
grep -A 20 "DOC-XX" review-master.md
grep -A 20 "DOC-XX" review-patch-pdf.md
```

### Step 2 — 列出本 DOC 的修订清单

对应本文档 §4-13 的"修订清单"表格,列出所有要改的位置。

### Step 3 — 拷贝到工作目录

```bash
cp /mnt/project/DOC-XX-v3...md ./DOC-XX-v4.md
```

### Step 4 — 逐处修订(保留原文 99%)

**用 `str_replace` 或等效精确替换**,每处修订必须:
- old_str:从原文中精确取出,保留原有所有内容
- new_str:在原有文本基础上**追加**或**替换**具体字段,不删除无关内容
- 每次修订对应 review 中的一个具体点

### Step 5 — 补附录 A

在文档末尾、`> **文档维护说明**` 之前,插入:

```markdown
---

## 附录 A: v4 修订清单

本次修订共 N 处精确修补,对应 Batch X-Y review + PDF 补丁 + Master:

| # | 位置 | 修订内容 | 来源 |
|---|---|---|---|
| 1 | §X.Y | ... | Batch X §XXX |
| ... | ... | ... | ... |
```

### Step 6 — 自检

按本文档 §1.2 的 9 条硬铁律逐条检查。

---

## 3. 跨文档全局修订点

所有 DOC 都要遵守以下全局变更:

### 3.1 版本/日期/头部元信息

```markdown
# 每份 DOC 的 Header 都改成:

> **文档编号**: DOC-XX
> **版本**: 4.0(Review 修订版)
> **日期**: 2026-04-18
> **性质**: (原文保留)
> **前置依赖**: DOC-00 v4, DOC-01 v4, DOC-02 v4, ...(对应的 v4)
> **v4 变更摘要**: 基于 5 轮 review 修订,N 处精确修补(详见文末 §附录 A)
```

### 3.2 文末维护说明

```markdown
> **文档维护说明**: ...(原文保留)
> **最后更新**: 2026-04-18 (v4 review 修订版) | **下一步**: DOC-XX+1 ...
```

### 3.3 交叉引用更新

所有 "DOC-XX v3" 改成 "DOC-XX v4",比如:
- "见 DOC-01 v3 §9.1" → "见 DOC-01 v4 §9.1"
- "参考 DOC-00 v3 §7" → "参考 DOC-00 v4 §7"

### 3.4 结构化日志/Prometheus/OTel 采集点

每个 Task 的 Part B 实现规范里,涉及业务逻辑的地方都要加:
- `logger = structlog.get_logger()` + `logger.info("event.name", **ctx)`
- `prism_xxx_total.labels(...).inc()` / `prism_xxx_duration_seconds.observe(...)`
- `with tracer.start_as_current_span("operation"):`

这些不必改写每行代码,**在 Part B 开头加一段总括**:

```markdown
> **v4 Observability 采集要求(本 Task 所有代码适用)**:
> - 所有 logger 用 `structlog.get_logger()`,事件名 `{domain}.{action}`
> - 业务关键路径(工具调用/回调/权限决策/熔断/Compaction)必须有 Prometheus counter + histogram
> - 跨进程操作(subprocess 启动/模型请求/子工具调用)必须有 OTel trace span
> - 详细规范见 DOC-12 Task 12.4/12.5/12.6
```

### 3.5 所有 14 张表 → 19 张表

任何地方出现 "14 张表" 改为 "19 张表"。

### 3.6 ENCRYPTION_KEY / JWT_SECRET / CALLBACK_SECRET 三独立

任何加密/签名地方明确使用的密钥名称:
- JWT 签名 → `JWT_SECRET`
- 子进程回调 HMAC → `CALLBACK_SECRET`
- Provider API Key 加密 → `ENCRYPTION_KEY`(AES-256-GCM)

不得混用。

### 3.7 ADR 编号接续

全局 ADR 空间(DOC-00~12 共用):
- DOC-02 v4 用到 ADR-017
- DOC-03 v4 从 **ADR-020** 开始(留 ADR-018/019 给预留)
- DOC-04 从 ADR-030 开始
- DOC-05 从 ADR-040 开始
- DOC-06 从 ADR-050 开始
- DOC-07 从 ADR-060 开始
- DOC-08 从 ADR-070 开始
- DOC-09 从 ADR-080 开始
- DOC-10 从 ADR-090 开始
- DOC-11 从 ADR-100 开始
- DOC-12 从 ADR-110 开始

---

## 4. DOC-03 改写指令

**Agent Runtime & Harness Core** — 最核心、最大(80KB → 预计 130KB)、Batch 2 问题最多。

### 4.1 修订清单(35 处)

| # | 位置 | 修订内容 | 来源 |
|---|---|---|---|
| 1 | Header | 版本/日期/v4 摘要 | 全局 |
| 2 | Task 3.1 Part A | 新增 ADR-020(Harness 单实例)/ADR-021(工具并行 gather)/ADR-022(Redis 直通)/ADR-023(心跳)/ADR-024(MAX_TURNS 按 agent_type 分档) | Batch 2 §A3-1 / Master M1 M2 M3 |
| 3 | Task 3.1 Part A 数据流图 | 重写:加 4 钩点 / 工具并行 / Redis 直通 / permission ask BLPOP / 心跳启停 | 同上 |
| 4 | Task 3.1 Part A 验收标准 | 加工具并行 / Redis 直通 / HTTP 关键事件 / 心跳 / permission ask / MAX_TURNS 按 agent_type | 同上 |
| 5 | Task 3.1 backend_callback.py | **重写为方案 A 双通道**(Redis 直通 + HTTP 带 3 次重试 + dead letter queue) | Batch 1 §3.3 D3 / Master M2 |
| 6 | Task 3.1 query_engine.py `_execute_tools` | 改为 `asyncio.gather` 并行(按依赖关系分组) | Batch 2 §A3-1 / PDF 补丁 |
| 7 | Task 3.1 query_engine.py `_process_turn` | 加 tool_use_delta Redis 直通 / message_complete / stream 接受 session_id | 同上 |
| 8 | Task 3.1 `__main__.py` 启动 | 加心跳 writer task(asyncio.create_task) | Batch 2 §B-2 / Batch 3 B3-2 |
| 9 | Task 3.1 验证步骤 | 加工具并行时序断言 / Redis PUBLISH 断言 / 心跳 Key 存在检查 | 同上 |
| 10 | Task 3.2 Part A | Middleware 从 2 钩点升到 **4 钩点**(pre_turn / pre_tool_use / post_tool_use / post_turn),ADR-025 | Batch 2 §A3-5 / PDF 补丁 |
| 11 | Task 3.2 middleware/base.py | Middleware 基类加 4 个钩点方法(原来只有 2 个) | 同上 |
| 12 | Task 3.2 middleware/pipeline.py | MiddlewarePipeline 调度 4 钩点的方法 | 同上 |
| 13 | Task 3.2 `_execute_tools` 集成 | 在工具执行前后加 pre_tool_use / post_tool_use 钩点调用 | 同上 |
| 14 | Task 3.3 Part A | **核心修订**:ADR-026(HookDecision 11 字段完整)/ADR-027(合并规则)/ADR-028(permission ask Redis BLPOP 协议) | PDF 补丁 P4 / Batch 2 §A3-6 A3-7 |
| 15 | Task 3.3 Part A Harness 交互 | 完整描述 permission ask 的三方协议(子进程 / Backend / Frontend) | Batch 2 §A3-7 |
| 16 | Task 3.3 hooks/decision.py(新文件) | `HookDecision` dataclass 完整 11 字段 + 合并规则函数 `merge_decisions()` | PDF 补丁 P4 |
| 17 | Task 3.3 hooks/handlers.py | Handler 返回 HookDecision 严格类型;加 4 种 handler 类型实现(command/http/prompt/agent) | 同上 |
| 18 | Task 3.3 permissions/engine.py | 加 `ask()` 方法:发 permission_ask 回调 + Redis BLPOP 等待 answer + 超时 fail-safe deny | Batch 2 §A3-7 |
| 19 | Task 3.3 permissions/ask_protocol.py(新文件) | Redis BLPOP 协议的完整实现:request 发起 / 超时处理 / answer 消费 | 同上 |
| 20 | Task 3.3 guardrails/platform_rules.py | 补完整的平台级护栏规则集(破坏性操作 + 速率 + PII + 跨用户) | Batch 2 §A3-8 |
| 21 | Task 3.3 验证步骤 | 加 permission ask 端到端测试(mock Redis BLPOP + 超时 + answer) | 同上 |
| 22 | Task 3.4 Part A | Feedback Loop 补丁:feedback 事件要结构化(event_type / severity / context) | Batch 2 §A3-8 |
| 23 | Task 3.4 feedback_capture.py | 结构化事件 + Redis TTL 配置 | 同上 |
| 24 | Task 3.4 lifecycle.py | SessionEnd Hook 触发 user_memory 提炼 + 写入 user_memories 表(通过 Backend 回调) | Batch 2 §A3-9 |
| 25 | Task 3.5 Part A | **核心修订**:ADR-029(Compaction 按回合组原子裁剪)+ 4 级策略完整定义 + ADR-030(is_skill_context 优先保留) | Batch 2 §A3-3 / Master M4 |
| 26 | Task 3.5 compaction.py | 4 级实现骨架:Tier 1 micro-compact / Tier 2 auto-compact / Tier 3 session memory / Tier 4 reactive truncation,每级以回合组为原子单元 | 同上 |
| 27 | Task 3.5 memory 层 | 6 层 Memory 结构定义 + Phase 1 只实现 Layer 1 (session) + Layer 2 (user_memories 表) | Batch 2 §A3-9 |
| 28 | Task 3.6 Part A | **简化修订**:配置源从 4 源砍到 2 源(代码默认 + harness_config.yaml);**删除 PATCH /harness/config 运行时 API**;删 toggle_middleware 运行时开关 | Batch 2 §A3-10 / Master M8 |
| 29 | Task 3.6 config_loader.py | 2 源合并策略代码;source_trace 记录每个字段来自哪一源 | 同上 |
| 30 | Task 3.6 API 端点 | GET /harness/config(readonly)保留 / **删除 PATCH** / reload 改为重启子进程才生效 | 同上 |
| 31 | 所有 Part B | 开头加 v4 Observability 采集要求说明(§3.4) | 全局 |
| 32 | 所有 ADR 编号 | 从 ADR-020 开始接续,DOC-02 v4 用到 017 | 全局 §3.7 |
| 33 | 交叉引用 | DOC-01 v3 → v4,DOC-02 v3 → v4 | 全局 |
| 34 | 附录 A | 完整修订清单表(~35 行) | SOP |
| 35 | 文末维护说明 | 更新日期 + 下一步 DOC-04 | 全局 |

### 4.2 关键代码骨架(必须逐字写入 PRD)

#### (A) HookDecision 11 字段(Task 3.3 hooks/decision.py)

```python
"""
HookDecision — Hook 执行结果的完整决策对象
对标 CC 的 src/services/tools/toolHooks.ts(11 个字段)
"""

from dataclasses import dataclass, field
from typing import Literal

PermissionDecision = Literal["allow", "ask", "deny"]

@dataclass
class HookDecision:
    """11 字段完整定义"""
    # 核心决策
    permission_decision: PermissionDecision | None = None
    # 输入改写
    updated_input: dict | None = None
    # MCP 工具输出改写
    updated_mcp_tool_output: dict | None = None
    # 流程控制
    prevent_continuation: bool = False
    stop: bool = False
    stop_reason: str | None = None
    # 追加上下文给 Agent
    additional_context: str | None = None
    # 用户消息(显示在 UI)
    message: str | None = None
    # 阻断性错误
    blocking_error: str | None = None
    # 审计
    reason: str | None = None
    handler_name: str | None = None


def merge_decisions(decisions: list[HookDecision]) -> HookDecision:
    """
    合并多个 Hook 的决策。
    严格度排序(高 → 低):
      stop > prevent_continuation > permission_deny > permission_ask > permission_allow
    
    updated_input 冲突时 abort(不猜),raise ValueError
    """
    result = HookDecision()
    
    # stop 优先级最高
    for d in decisions:
        if d.stop:
            result.stop = True
            result.stop_reason = d.stop_reason
            result.handler_name = d.handler_name
            return result  # 立即返回,不处理后续
    
    # prevent_continuation 次优先级
    for d in decisions:
        if d.prevent_continuation:
            result.prevent_continuation = True
            result.reason = d.reason
    
    # permission 按严格度:deny > ask > allow
    permission_priority = {"deny": 3, "ask": 2, "allow": 1, None: 0}
    result.permission_decision = max(
        (d.permission_decision for d in decisions),
        key=lambda p: permission_priority[p],
        default=None,
    )
    
    # updated_input 冲突检测
    updated_inputs = [d.updated_input for d in decisions if d.updated_input is not None]
    if len(updated_inputs) > 1:
        raise ValueError(f"Multiple hooks want to modify input, refusing to guess: {updated_inputs}")
    if updated_inputs:
        result.updated_input = updated_inputs[0]
    
    # updated_mcp_tool_output 同理
    updated_outputs = [d.updated_mcp_tool_output for d in decisions if d.updated_mcp_tool_output is not None]
    if len(updated_outputs) > 1:
        raise ValueError(f"Multiple hooks want to modify MCP output: {updated_outputs}")
    if updated_outputs:
        result.updated_mcp_tool_output = updated_outputs[0]
    
    # additional_context 拼接
    contexts = [d.additional_context for d in decisions if d.additional_context]
    if contexts:
        result.additional_context = "\n\n".join(contexts)
    
    # blocking_error 任一触发即阻断
    errors = [d.blocking_error for d in decisions if d.blocking_error]
    if errors:
        result.blocking_error = "; ".join(errors)
    
    # message 拼接
    messages = [d.message for d in decisions if d.message]
    if messages:
        result.message = "\n".join(messages)
    
    return result
```

#### (B) Permission ask Redis BLPOP 协议(Task 3.3 permissions/ask_protocol.py)

```python
"""
Permission Ask 反向通信协议(v4 新增)

子进程通过 Redis BLPOP 阻塞等待用户回答。
Backend 通过 SSE 把 harness_event(type=permission_ask)推给前端。
用户点击后 Backend POST /sessions/{id}/permission-answer,RPUSH 到 Redis。
子进程 BLPOP 返回 → 继续执行。

超时(默认 300s)默认 deny(fail-safe)。
"""

import asyncio
import uuid7
import json
from datetime import datetime, timedelta, timezone
import redis.asyncio as redis_async
from structlog import get_logger

logger = get_logger()

PERMISSION_ASK_TIMEOUT_SECONDS = 300  # 从环境变量读

class PermissionAskProtocol:
    def __init__(self, redis_url: str, callback: "BackendCallback"):
        self._redis = redis_async.from_url(redis_url, decode_responses=True)
        self._callback = callback
    
    async def ask(
        self,
        run_id: str,
        tool_name: str,
        tool_input: dict,
        reason: str,
        timeout_seconds: int = PERMISSION_ASK_TIMEOUT_SECONDS,
    ) -> Literal["allow", "deny"]:
        """
        发起 permission ask 请求,阻塞等待用户回答。
        返回 'allow' 或 'deny'。超时默认 deny(fail-safe)。
        """
        request_id = str(uuid7.create())
        answer_key = f"perm_answer:{request_id}"
        req_key = f"perm_req:{request_id}"
        timeout_at = datetime.now(timezone.utc) + timedelta(seconds=timeout_seconds)
        
        # 记录请求到 Redis(供查询)
        await self._redis.setex(
            req_key,
            timeout_seconds,
            json.dumps({
                "run_id": run_id,
                "tool_name": tool_name,
                "tool_input": tool_input,
                "reason": reason,
                "timeout_at": timeout_at.isoformat(),
            }),
        )
        
        # 通过回调推送 permission_ask 事件(Backend → SSE → 前端弹窗)
        await self._callback.permission_ask(
            request_id=request_id,
            tool_name=tool_name,
            tool_input=tool_input,
            reason=reason,
            timeout_at=timeout_at.isoformat(),
        )
        
        logger.info(
            "harness.permission_ask.pending",
            request_id=request_id,
            tool_name=tool_name,
            timeout_seconds=timeout_seconds,
        )
        
        # BLPOP 阻塞等待用户回答
        result = await self._redis.blpop(answer_key, timeout=timeout_seconds)
        
        if result is None:
            # 超时 → fail-safe deny
            logger.warning(
                "harness.permission_ask.timeout",
                request_id=request_id,
                tool_name=tool_name,
            )
            await self._callback.harness_event("permission_ask_timeout", {
                "request_id": request_id,
                "tool_name": tool_name,
            })
            return "deny"
        
        _, answer = result
        if answer not in ("allow", "deny"):
            logger.error(
                "harness.permission_ask.invalid_answer",
                request_id=request_id,
                answer=answer,
            )
            return "deny"
        
        logger.info(
            "harness.permission_ask.answered",
            request_id=request_id,
            tool_name=tool_name,
            decision=answer,
        )
        return answer
    
    async def close(self):
        await self._redis.aclose()
```

#### (C) Middleware 4 钩点(Task 3.2 middleware/base.py)

```python
"""
Middleware 抽象基类(v4:4 钩点)

4 钩点对应 TAOR 循环的 4 个观察/干预时机:
- pre_turn:   本轮 API 调用之前(可改写 messages / 注入上下文)
- pre_tool_use: 工具执行之前(可改写 tool_input / 决定 permission)
- post_tool_use: 工具执行之后(可改写 tool_result)
- post_turn:  本轮结束之后(可触发 compaction / 检测 loop)
"""

from abc import ABC
from dataclasses import dataclass
from typing import Any

@dataclass
class MiddlewareContext:
    """Middleware 调用上下文"""
    run_id: str
    session_id: str
    user_id: str
    turn_count: int
    agent_type: str
    messages: list          # 当前 messages
    system_prompt: str
    tool_use_block: Any = None        # pre_tool_use / post_tool_use 时有值
    tool_result_block: Any = None      # post_tool_use 时有值
    custom_data: dict = None          # middleware 之间传递数据

class Middleware(ABC):
    """所有 Middleware 继承此类,按需 override 钩点"""
    
    name: str = "unnamed"
    
    async def pre_turn(self, ctx: MiddlewareContext) -> None:
        """本轮 API 调用之前"""
        pass
    
    async def pre_tool_use(self, ctx: MiddlewareContext) -> None:
        """工具执行之前"""
        pass
    
    async def post_tool_use(self, ctx: MiddlewareContext) -> None:
        """工具执行之后"""
        pass
    
    async def post_turn(self, ctx: MiddlewareContext) -> None:
        """本轮结束之后(含 compaction 检查)"""
        pass
```

#### (D) 工具并行执行骨架(Task 3.1 query_engine.py `_execute_tools`)

```python
async def _execute_tools(self, tool_use_blocks: list[ToolUseBlock]) -> None:
    """
    执行工具调用列表(v4:并行化)
    
    策略:
    1. 按依赖关系分组(无依赖可并行,有依赖顺序执行)
    2. 无依赖组 → asyncio.gather
    3. 有依赖组 → 顺序 for
    
    依赖检测:若 ToolUseBlock.input 中包含 `{{tool_result:X}}` 占位符,
    则依赖 id=X 的工具。目前保守实现:所有 tool 无依赖 → 全部并行。
    DOC-04 Coordinator 模式下可精细化依赖分析。
    """
    # 简单实现:所有工具并行
    tool_coros = [
        self._execute_single_tool(block)
        for block in tool_use_blocks
    ]
    results = await asyncio.gather(*tool_coros, return_exceptions=True)
    
    # 收集结果到 tool_result user message(canonical Anthropic 语义)
    result_blocks = []
    for block, result in zip(tool_use_blocks, results):
        if isinstance(result, Exception):
            result_blocks.append(ToolResultBlock(
                tool_use_id=block.id,
                content=f"工具异常: {str(result)}",
                is_error=True,
            ))
        else:
            result_blocks.append(result)
    
    # 追加一条 user message(含所有 tool_result)
    self._messages.append(PrismMessage(
        role="user",
        content=result_blocks,
    ))

async def _execute_single_tool(self, block: ToolUseBlock) -> ToolResultBlock:
    """单工具执行,走完整 Pipeline(含 Hook / Permission)"""
    await self._callback.tool_start(block.id, block.name, block.input)
    start_time = time.monotonic()
    
    try:
        # 走 ToolExecutionPipeline(含 Hook / Permission / 执行 / 截断)
        result = await self._pipeline.execute(
            tool_name=block.name,
            tool_input=block.input,
            tool_use_id=block.id,
            run_context=self._run_context,  # v4 新增:传递 run_id/session_id/user_id
        )
        duration_ms = int((time.monotonic() - start_time) * 1000)
        await self._callback.tool_end(
            tool_use_id=block.id,
            output=result.content,
            is_error=result.is_error,
            duration_ms=duration_ms,
        )
        return result
    except Exception as e:
        duration_ms = int((time.monotonic() - start_time) * 1000)
        await self._callback.tool_end(
            tool_use_id=block.id,
            output=str(e),
            is_error=True,
            duration_ms=duration_ms,
        )
        raise
```

#### (E) 心跳 writer task(Task 3.1 `__main__.py`)

```python
"""
executor/__main__.py v4 补充:心跳 writer
"""
import asyncio
import redis.asyncio as redis_async
import os

HEARTBEAT_INTERVAL = int(os.environ.get("HEARTBEAT_INTERVAL_SECONDS", "5"))

async def heartbeat_writer(run_id: str, redis_url: str, stop_event: asyncio.Event):
    """
    每 5s 向 Redis 写心跳,直到 stop_event 被 set。
    Key: harness:heartbeat:{run_id}, TTL 60s(远大于 HEARTBEAT_STALE_SECONDS=30)
    Backend HeartbeatMonitor 扫描,超过 30s 无心跳 → 标记 crashed
    """
    r = redis_async.from_url(redis_url)
    try:
        while not stop_event.is_set():
            try:
                await r.setex(
                    f"harness:heartbeat:{run_id}",
                    60,  # TTL 60s
                    str(int(time.time())),
                )
            except Exception:
                pass  # 心跳失败不中断 Agent
            
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=HEARTBEAT_INTERVAL)
            except asyncio.TimeoutError:
                continue
    finally:
        await r.delete(f"harness:heartbeat:{run_id}")
        await r.aclose()


async def main():
    # ... 原有参数解析 ...
    
    stop_event = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        heartbeat_writer(run_id, redis_url, stop_event)
    )
    
    try:
        # ... 原有 QueryEngine.run() ...
        await engine.run(user_prompt)
    finally:
        stop_event.set()
        await heartbeat_task
```

#### (F) Compaction 回合组原子裁剪(Task 3.5 compaction.py)

```python
"""
4 级渐进式 Compaction Pipeline(v4)

Tier 1 — micro-compact(关键词触发)
  触发: 上下文使用率 ≥ 60%
  策略: 裁掉最老的 1 个回合组,保留所有 is_skill_context

Tier 2 — auto-compact(阈值触发)
  触发: 上下文使用率 ≥ 85%
  策略: LLM 生成历史摘要替换最老的 50% 回合组

Tier 3 — session memory(SessionEnd 时触发)
  触发: SessionEnd Hook
  策略: 提炼本 session 要点 → user_memories 表

Tier 4 — reactive truncation(紧急兜底)
  触发: API 报 context_too_long 错误
  策略: 强制裁到最近 3 个回合组 + skill_context
"""

from dataclasses import dataclass
from executor.adapters.base import PrismMessage

class CompactionPipeline:
    def __init__(
        self,
        budget: ContextBudgetManager,
        callback: BackendCallback,
        adapter: ModelAdapter,    # Tier 2 用 LLM 生成摘要
    ):
        self._budget = budget
        self._callback = callback
        self._adapter = adapter
    
    async def maybe_compact(
        self,
        messages: list[PrismMessage],
        system_prompt: str,
    ) -> list[PrismMessage]:
        """入口:根据阈值决定是否触发哪一级 Compaction"""
        current = self._budget.estimate_messages_tokens(messages, system_prompt)
        max_tokens = self._budget._max_context_tokens - self._budget._reserve_for_response
        usage_ratio = current / max_tokens
        
        if usage_ratio >= 0.85:
            return await self._tier2_auto_compact(messages, system_prompt, current)
        elif usage_ratio >= 0.60:
            return self._tier1_micro_compact(messages, current)
        return messages
    
    def _tier1_micro_compact(self, messages: list[PrismMessage], before_tokens: int) -> list[PrismMessage]:
        """Tier 1: 裁最老 1 个回合组"""
        groups = self._budget.identify_turn_groups(messages)
        if len(groups) <= 2:
            return messages
        
        # 保留第 2 组到最后 + 所有 is_skill_context 消息
        to_keep = set()
        for start, end in groups[1:]:
            to_keep.update(range(start, end + 1))
        
        result = [msg for i, msg in enumerate(messages) if i in to_keep or msg.is_skill_context]
        
        after_tokens = self._budget.estimate_messages_tokens(result, "")
        asyncio.create_task(self._callback.compaction_in_progress(
            tier=1,
            before_tokens=before_tokens,
            after_tokens=after_tokens,
        ))
        return result
    
    async def _tier2_auto_compact(
        self,
        messages: list[PrismMessage],
        system_prompt: str,
        before_tokens: int,
    ) -> list[PrismMessage]:
        """Tier 2: LLM 摘要替换最老的 50% 回合组"""
        groups = self._budget.identify_turn_groups(messages)
        if len(groups) <= 3:
            return messages
        
        split_point = len(groups) // 2
        old_groups = groups[:split_point]
        recent_groups = groups[split_point:]
        
        # 收集要摘要的消息 + is_skill_context 要保留
        old_indices = set()
        for start, end in old_groups:
            old_indices.update(range(start, end + 1))
        old_messages = [
            msg for i, msg in enumerate(messages)
            if i in old_indices and not msg.is_skill_context
        ]
        
        # LLM 生成摘要
        summary_prompt = "请将以下对话历史凝练为 200 字内的摘要,保留关键决策、工具调用结果、未完成事项:\n\n"
        for msg in old_messages:
            summary_prompt += f"{msg.role}: {msg.content}\n\n"
        
        summary_response = await self._adapter.complete(
            messages=[PrismMessage(role="user", content=[TextBlock(text=summary_prompt)])],
            system_prompt="你是对话历史压缩工具。只输出摘要,不说其他。",
            max_tokens=500,
        )
        summary_text = summary_response.messages[0].content[0].text
        
        # 构造新 messages:摘要消息 + 保留的回合组 + skill_context
        result = [
            PrismMessage(
                role="user",
                content=[TextBlock(text=f"[历史对话摘要]\n{summary_text}")],
            )
        ]
        
        recent_indices = set()
        for start, end in recent_groups:
            recent_indices.update(range(start, end + 1))
        
        for i, msg in enumerate(messages):
            if i in recent_indices:
                result.append(msg)
            elif msg.is_skill_context:
                result.append(msg)
        
        after_tokens = self._budget.estimate_messages_tokens(result, system_prompt)
        await self._callback.compaction_in_progress(
            tier=2,
            before_tokens=before_tokens,
            after_tokens=after_tokens,
        )
        return result
```

### 4.3 DOC-03 预期产出

- 文件:`DOC-03-v4.md`
- 预计行数:~2900 行(从 2189 扩展)
- 预计大小:~130KB

---

## 5. DOC-04 改写指令

**Agent Orchestration** — 5 Task,含新 Task 4.5 PluginBuilder。

### 5.1 修订清单(22 处)

| # | 位置 | 修订内容 | 来源 |
|---|---|---|---|
| 1 | Header | 版本/日期/v4 摘要 | 全局 |
| 2 | Task 4.1 Part A(Agent 定义) | 新增 ADR-030(agent-scoped MCP 白名单)/ADR-031(agent-specific frontmatter skills)/ADR-032(Verifier VERDICT 协议强制) | PDF 补丁 P7 P10 / Batch 2 §A4-1 |
| 3 | Task 4.1 Agent 定义结构 | AgentDefinition 加 `mcp_servers: list[str]` + `frontmatter_skills: list[str]` 字段 | 同上 |
| 4 | Task 4.1 verifier.py | **Verifier 完整 prompt** — VERDICT: PASS/FAIL/PARTIAL 强制格式 + try-to-break 反制 + 4 类变更验证(frontend/backend/CLI/migration) | PDF 补丁 P3 |
| 5 | Task 4.1 explore/research.py | Bash 白名单严格定义:`ls, git status, git log, git diff, find, grep, cat, head, tail`(其他禁用) | PDF 补丁 P3 |
| 6 | Task 4.1 planner.py | 输出必须含 "Critical Files for Implementation" 清单 | 同上 |
| 7 | Task 4.2 Part A(Fork) | 新增 ADR-033(Fork capability-based 白名单)/ADR-034(Fork 3 条 prompt-level 约束)/ADR-035(ForkBriefing 结构化) | PDF 补丁 P2 P7 / Batch 2 §A4-2 |
| 8 | Task 4.2 ForkBriefing dataclass(新结构) | `goal/why/excluded/context/expected_output/file_references` 6 字段 | PDF 补丁 P7 |
| 9 | Task 4.2 Fork Agent prompt | 3 条硬约束:禁止覆盖 model / 禁止偷窥 outputFile / 禁止预言结果 | PDF 补丁 P2 |
| 10 | Task 4.2 fork_manager.py | capability-based 白名单(能力列表过滤,非工具名列表)+ 深度限制 + timeout | Batch 2 §A4-2 |
| 11 | Task 4.3 Part A(Coordinator) | 新增 ADR-036(Coordinator Plan checkpoint 持久化)+ 支持崩溃恢复 | Batch 2 §A4-3 / Master M3 |
| 12 | Task 4.3 coordinator.py | 每个 step 开始/完成时 checkpoint 到 `coordinator_plans` 表 | 同上 |
| 13 | Task 4.3 `POST /runs/{id}/resume` 集成 | Coordinator Recovery 从 current_step_index 恢复 | 同上 |
| 14 | Task 4.4 Part A(TaskRouter) | 保留关键词匹配骨架 + ADR-037(LLM 分类 fallback Phase 2) | Batch 2 §A4-4 |
| 15 | Task 4.4 路由表 | Agent 类型扩展到 6 种(含 coordinator / plugin_builder) | 全局 |
| 16 | **Task 4.5 PluginBuilder 重大修订** | 删除"硬编码 5 轮对话"策略 → 改为"需求完整度打分"动态决定 + ADR-038 | Batch 2 §A4-5 / Master M8 |
| 17 | Task 4.5 打分函数 | `score_requirement_completeness(conversation) -> float` + 阈值 0.8 触发生成 | 同上 |
| 18 | Task 4.5 Guardrail | Platform Guardrail 降级为可配置(scope / 触发条件 / 降级处理) | 同上 |
| 19 | 所有 Part B 开头 | 加 v4 Observability 采集要求说明 | 全局 §3.4 |
| 20 | ADR 编号 | ADR-030~039 | 全局 |
| 21 | 交叉引用 | v3 → v4 | 全局 |
| 22 | 附录 A + 文末 | 修订清单 + 下一步 DOC-05 | SOP |

### 5.2 关键代码骨架

#### (A) Verifier 完整 prompt(Task 4.1 verifier.py)

```python
"""
Verifier Agent - 对抗性验证者
核心使命: "try to break it" - 不假设成功,主动寻找失败
对标 CC: src/tools/AgentTool/built-in/verificationAgent.ts
"""

VERIFIER_SYSTEM_PROMPT = """你是 Verification Agent,对抗性验证者。

**你的使命**: try to break it —— 不要假设一切正常,主动寻找失败。

**两种必须警惕的失败模式**:

1. **Verification Avoidance** — 只看代码不跑命令。
   你不能只读代码判断"看起来对",必须实际执行 build / test / linter / type-check,
   把 command 和 output 记录在报告里。

2. **Front-80% Illusion** — 被前 80% 迷惑。
   主要路径跑通不代表验证完成。必须做 adversarial probes:
   - 边界输入(空、极大、特殊字符、畸形)
   - 错误路径(失败场景、超时、权限拒绝)
   - 并发/竞态(多请求同时、顺序依赖)
   - 兼容性(旧版本数据、不同 Provider)

**按变更类型做专项验证**:

- **Frontend 变更**: 浏览器自动化(Playwright 截图 + 交互)。不能只看 Console 无报错
- **Backend 变更**: curl / fetch 实测端点,验证 HTTP 状态 + 响应体 + 数据库落库
- **CLI 变更**: 看 stdout / stderr / exit code 三要素
- **Migration**: 测 up + 测 down + 测重复 up(幂等)

**你必须生成的验证报告格式**:

```
## 验证清单

### 1. 编译/类型检查
Command: {cmd}
Output: {obs}
Status: PASS | FAIL

### 2. 单元测试
Command: {cmd}
Output: {obs}
Status: PASS | FAIL

### 3. {其他按变更类型的专项验证}
...

## 边界探测

- {探测项 1}: {结果}
- {探测项 2}: {结果}
...

## VERDICT: {PASS | FAIL | PARTIAL}

- PASS: 所有验证项通过,未发现问题
- FAIL: 核心功能有 bug,不能交付
- PARTIAL: 主路径通,但边界或次要功能有问题(列出具体)
```

**最终必须输出 VERDICT 三态结论之一,不能模棱两可。**
"""
```

#### (B) Coordinator Plan checkpoint(Task 4.3 coordinator.py)

```python
"""
Coordinator Plan 持久化 checkpoint
每个 step 开始/完成时通过 Backend 回调写入 coordinator_plans 表
"""

class CoordinatorEngine:
    async def run_plan(self, plan: CoordinatorPlan) -> CoordinatorResult:
        """执行 Plan,每步 checkpoint"""
        
        # 初始 checkpoint
        await self._callback.coordinator_plan_update(
            plan_id=plan.id,
            current_step=0,
            total_steps=len(plan.steps),
            status="running",
        )
        
        step_results = []
        for i, step in enumerate(plan.steps):
            # Step 开始 checkpoint
            await self._callback.coordinator_plan_update(
                plan_id=plan.id,
                current_step=i,
                total_steps=len(plan.steps),
                status="running",
                step_results=step_results,
            )
            
            # 执行 step(fork 子 agent)
            try:
                result = await self._execute_step(step)
                step_results.append(result)
            except Exception as e:
                await self._callback.coordinator_plan_update(
                    plan_id=plan.id,
                    current_step=i,
                    total_steps=len(plan.steps),
                    status="failed",
                    step_results=step_results,
                    error=str(e),
                )
                raise
        
        # 完成 checkpoint
        await self._callback.coordinator_plan_update(
            plan_id=plan.id,
            current_step=len(plan.steps),
            total_steps=len(plan.steps),
            status="completed",
            step_results=step_results,
        )
        
        return CoordinatorResult(steps=step_results)
    
    @classmethod
    async def resume_from_checkpoint(cls, run_id: str, db_session) -> "CoordinatorEngine":
        """从 coordinator_plans 表恢复执行状态"""
        checkpoint = db_session.query(CoordinatorPlan).filter_by(run_id=run_id).first()
        if not checkpoint:
            raise ValueError(f"No checkpoint for run {run_id}")
        
        engine = cls(...)
        engine._resume_from_step = checkpoint.current_step_index
        engine._previous_results = checkpoint.step_results
        return engine
```

#### (C) PluginBuilder 完整度打分(Task 4.5)

```python
"""
Plugin Builder - 需求完整度打分
v4:删除"硬编码 5 轮"策略,改为动态打分
"""

class RequirementCompleteness:
    """插件需求完整度维度"""
    
    CRITERIA = {
        "plugin_name": 0.15,              # 插件名(唯一标识)
        "purpose": 0.20,                   # 目的/解决什么问题
        "tools_or_skills": 0.25,           # 提供哪些工具 / skill
        "input_output": 0.15,              # 输入输出样例
        "error_handling": 0.10,            # 错误处理策略
        "permission_boundary": 0.10,       # 权限边界(哪些操作需要 ask)
        "examples": 0.05,                   # 用例场景
    }
    
    @classmethod
    async def score(
        cls,
        conversation: list[PrismMessage],
        adapter: ModelAdapter,
    ) -> dict:
        """
        用 LLM 分析对话,对每个维度打 0/0.5/1 分
        返回 {criterion: score, overall: weighted_sum}
        阈值 0.8 触发生成(PluginBuilder 认为信息够了)
        """
        analysis_prompt = f"""分析以下对话,判断用户是否已提供足够信息构建插件。
        
对每个维度给分(0=缺失 / 0.5=部分 / 1=清晰):
{chr(10).join(f'- {k}: {v*100:.0f}%' for k, v in cls.CRITERIA.items())}

对话:
{format_conversation(conversation)}

只输出 JSON,格式:
{{"plugin_name": 1.0, "purpose": 1.0, "tools_or_skills": 0.5, ...}}
"""
        
        response = await adapter.complete(
            messages=[PrismMessage(role="user", content=[TextBlock(text=analysis_prompt)])],
            system_prompt="你是信息完整度评估工具,只输出 JSON",
            max_tokens=300,
        )
        
        scores = json.loads(response.messages[0].content[0].text)
        overall = sum(scores[k] * cls.CRITERIA[k] for k in cls.CRITERIA)
        scores["overall"] = overall
        return scores


class PluginBuilderAgent:
    COMPLETENESS_THRESHOLD = 0.8
    
    async def run(self, user_request: str):
        """
        循环:
          1. 用户说话
          2. 打分
          3. 若 >= 0.8 → 生成插件 + 结束
          4. 若 < 0.8 → 问最缺的维度 + 回到 1
        """
        conversation = [PrismMessage(role="user", content=[TextBlock(text=user_request)])]
        
        while True:
            scores = await RequirementCompleteness.score(conversation, self._adapter)
            
            if scores["overall"] >= self.COMPLETENESS_THRESHOLD:
                # 完整度够,生成插件
                return await self._generate_plugin(conversation)
            
            # 找最缺的维度,问用户
            missing_dim = min(
                (k for k in RequirementCompleteness.CRITERIA if k != "overall"),
                key=lambda k: scores.get(k, 0),
            )
            question = self._ask_about(missing_dim)
            conversation.append(PrismMessage(role="assistant", content=[TextBlock(text=question)]))
            
            # 等待用户回答(通过 SSE 推 + 阻塞等)
            user_reply = await self._wait_for_user_reply()
            conversation.append(PrismMessage(role="user", content=[TextBlock(text=user_reply)]))
```

### 5.3 DOC-04 预期产出

- 文件:`DOC-04-v4.md`
- 预计行数:~2500 行
- 预计大小:~100KB

---

## 6. DOC-05 改写指令

**Plugin Ecosystem** — 5 Task(Skill / Hook / MCP / Plugin + v3.1 新 Task 5.5-5.7 Skills Market)。

### 6.1 修订清单(28 处)

| # | 位置 | 修订内容 | 来源 |
|---|---|---|---|
| 1 | Header | 版本/日期/v4 摘要 | 全局 |
| 2 | Task 5.1 Part A(Skill) | 新增 ADR-040(Skill 三级加载规范)/ADR-041(Skill 匹配时强制执行,不能只提不调用)/ADR-042(is_skill_context 标记) | PDF 补丁 P6 / Batch 2 §A5-1 |
| 3 | Task 5.1 skill_loader.py | Level 0/1/2 加载机制 + 匹配规则 + 注入 `<skill_context name="X">` tag 标记 | 同上 |
| 4 | Task 5.1 skill_grammar section 联动 | 引用 DOC-02 v4 Task 2.4 的 skill_grammar_section | PDF 补丁 P6 |
| 5 | Task 5.2 Part A(Hook) | 保留原设计 + ADR-043(Hook 4 种 handler 类型:command/http/prompt/agent) | Batch 2 §A5-2 |
| 6 | Task 5.2 hook_runner.py | 4 种 handler 实现骨架 | 同上 |
| 7 | Task 5.3 Part A(MCP) | 新增 ADR-044(MCP instructions 双通道注入)/ADR-045(agent-scoped MCP 白名单) | PDF 补丁 P5 / Batch 2 §A5-3 |
| 8 | Task 5.3 mcp_client.py | 读取 MCP Server 的 instructions 字段 → 传给 PromptAssembler | PDF 补丁 P5 |
| 9 | Task 5.3 agent-scoped | AgentDefinition 的 mcp_servers 字段过滤 | 同上 |
| 10 | Task 5.4 Part A(Plugin Host) | 新增 ADR-046(Plugin 命名空间 + 变量替换系统) | PDF 补丁 P9 / Batch 2 §A5-4 |
| 11 | Task 5.4 变量替换 | `${PRISM_PLUGIN_ROOT}` / `${PRISM_PLUGIN_DATA}` / `${PRISM_SKILL_DIR}` / `${PRISM_SESSION_ID}` / `${user_config.X}` + CC 兼容映射(`${CLAUDE_*}`) | PDF 补丁 P9 |
| 12 | Task 5.4 Plugin 加载顺序 | Platform → User → Session 三级 + 冲突检测 | Batch 2 §A5-4 |
| 13 | **Task 5.5 重大修订(Skills Registry)** | Phase 1 只上 Local + GitHub **两源**,删 Manus / npm(Phase 2 再加) | Master M8 / Batch 2 §A5-5 |
| 14 | Task 5.5 SkillSource 抽象 | `LocalSource` + `GitHubSource` 完整实现 + 剔除 `ManusSource` / `NpmSource` 占位 | 同上 |
| 15 | Task 5.5 搜索 API | `/skills/search?q=X&source=local|github` | 同上 |
| 16 | **Task 5.6 重大修订(Skills CLI + Agent Tool)** | Agent Tool **只保留 search**,不给 install 权限(权限边界) | Master M8 |
| 17 | Task 5.6 skill_install_service | Backend 写 `skill_installs` 表(DOC-01 v4 §4.2 新增) | Batch 3 §A9-4 |
| 18 | Task 5.6 搜索工具 | Agent 可通过 `skills_search(query)` 工具搜索,但安装仍需用户手动触发 | 同上 |
| 19 | **Task 5.7 重大修订(CC 兼容层)** | `export_to_cc` 返回 `ConversionReport`(不是直接文件)+ plugin.yaml schema 严格化 | Master M8 / Batch 2 §A5-7 |
| 20 | Task 5.7 ConversionReport | `lost_fields: list[str]` + `warnings: list[str]` + `cc_compat_zip: bytes` | 同上 |
| 21 | Task 5.7 plugin.yaml schema | Pydantic 严格校验 + 缺字段 422 | 同上 |
| 22 | 所有 Part B 开头 | v4 Observability 采集说明 | 全局 |
| 23 | Redis namespace | Skills 安装状态 Redis key 规范(skill_install:status:{user_id}:{skill_name}) | Batch 3 §B3-I |
| 24 | Prometheus metrics | prism_skill_installs_total / prism_skill_searches_total | Batch 5 §B5-I |
| 25 | 结构化日志 | skill.installed / skill.uninstalled / skill.loaded / mcp.instructions_injected | 同上 |
| 26 | ADR 编号 | ADR-040~049 | 全局 |
| 27 | 交叉引用 | v3 → v4 | 全局 |
| 28 | 附录 A + 文末 | 修订清单 + 下一步 DOC-06 | SOP |

### 6.2 DOC-05 预期产出

- 文件:`DOC-05-v4.md`
- 预计行数:~2300 行
- 预计大小:~95KB

---

## 7. DOC-06 改写指令

**Backend Auth & User** — 2 Task。改动相对小。

### 7.1 修订清单(10 处)

| # | 位置 | 修订内容 | 来源 |
|---|---|---|---|
| 1 | Header | 版本/日期/v4 摘要 | 全局 |
| 2 | Task 6.1 Part A | 新增 ADR-050(三密钥独立)/ADR-051(SSE ticket 替代 URL query JWT) | Batch 1 v2 §3.6 / Batch 3 §A6-1 |
| 3 | Task 6.1 启动校验 | `validate_secrets()` 函数 + main.py lifespan 调用 | 同上 |
| 4 | Task 6.1 sse_ticket_service.py(新文件) | `generate_ticket(user_id, session_id) -> str` + `verify_and_consume_ticket(ticket, session_id) -> str` | Batch 3 §A6-2 |
| 5 | Task 6.1 `POST /auth/sse-ticket` 端点 | 新增,Body: `{session_id}`, Return: `{ticket, expires_at}` | 同上 |
| 6 | Task 6.1 security.py | `encrypt_api_key()` / `decrypt_api_key()` AES-256-GCM 完整实现(用 ENCRYPTION_KEY) | DOC-02 Task 2.3 引用 |
| 7 | Task 6.2 Part A | 邀请码逻辑保留,加审计日志结构化 | Batch 3 §A6-3 |
| 8 | 所有 Part B 开头 | v4 Observability 采集说明 + Prometheus auth metrics | 全局 |
| 9 | ADR 编号 | ADR-050~055 | 全局 |
| 10 | 附录 A + 文末 | 修订清单 + 下一步 DOC-07 | SOP |

### 7.2 关键代码骨架

#### (A) SSE Ticket Service(Task 6.1)

```python
"""
SSE Ticket Service - 一次性 SSE 认证 ticket
"""

import uuid7
from datetime import datetime, timedelta, timezone
import redis.asyncio as redis_async

class SSETicketService:
    def __init__(self, redis_client, settings):
        self._redis = redis_client
        self._ttl = settings.SSE_TICKET_TTL_SECONDS  # 60s
    
    async def generate_ticket(self, user_id: str, session_id: str) -> dict:
        """生成 ticket,存入 Redis 一次性消费"""
        ticket = str(uuid7.create())
        key = f"sse_ticket:{ticket}"
        data = {"user_id": user_id, "session_id": session_id}
        
        await self._redis.setex(key, self._ttl, json.dumps(data))
        
        return {
            "ticket": ticket,
            "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=self._ttl)).isoformat(),
        }
    
    async def verify_and_consume(self, ticket: str, session_id: str) -> str:
        """验证并消费 ticket(原子 DEL),返回 user_id 或抛异常"""
        key = f"sse_ticket:{ticket}"
        
        # Atomic GETDEL
        raw = await self._redis.getdel(key)
        if not raw:
            raise HTTPException(401, "Invalid or expired SSE ticket")
        
        data = json.loads(raw)
        if data["session_id"] != session_id:
            raise HTTPException(403, "Ticket session_id mismatch")
        
        return data["user_id"]
```

---

## 8. DOC-07 改写指令

**Backend Session-Run-Task** — 4 Task。Backend 最大、改动最多的一份。

### 8.1 修订清单(25 处)

| # | 位置 | 修订内容 | 来源 |
|---|---|---|---|
| 1 | Header | 版本/日期/v4 摘要 | 全局 |
| 2 | Task 7.1 Part A | 无大改,只需 text_preview 生成规则同步 DOC-01 v4 §4.2 messages 表 | Batch 3 §A7-1 |
| 3 | Task 7.1 session_service | `generate_text_preview(role, content, tool_lookup)` 按规则生成 | 同上 |
| 4 | **Task 7.2 Part A 重大修订** | 新增 ADR-060(sequence_no 并发原子性)/ADR-061(promote 原子事务)/ADR-062(Run cancel 三模式 graceful/force/also_cancel_queue) | Batch 3 §A7-2 §B3-4 |
| 5 | Task 7.2 sequence_no 原子性实现 | PostgreSQL per-session sequence 或 advisory_xact_lock + max+1 的完整 SQL 代码 | 同上 |
| 6 | Task 7.2 Run cancel | graceful(等当前 tool 执行完)/force(立即 SIGKILL)/also_cancel_queue(取消后续排队) | Batch 3 §A7-2 |
| 7 | **Task 7.3 Part A 重大修订** | 新增 ADR-063(回调协议方案 A)/ADR-064(permission-answer 端点)/ADR-065(HeartbeatMonitor 崩溃恢复) | Batch 1 §3.3 D3 / Batch 2 §A3-7 / Batch 3 B3-1 B3-2 |
| 8 | Task 7.3 callback_service.py | 重写接收逻辑:Redis 订阅 text_delta / tool_use_delta + HTTP 接收关键事件 + 按事件类型路由持久化 | Master M2 |
| 9 | Task 7.3 `POST /sessions/{id}/permission-answer` 端点(新) | Body: `{request_id, decision}`,Backend 同时写 permission_requests 表 status + Redis RPUSH `perm_answer:{request_id}` | Batch 2 §A3-7 |
| 10 | Task 7.3 heartbeat_monitor.py(新文件) | 后台 task,每 10s 扫描 `harness:heartbeat:*`,超 30s 无心跳 → 标记 Run crashed + promote 队列 | Batch 3 B3-2 |
| 11 | Task 7.3 `POST /internal/run-crashed` 端点(新) | HeartbeatMonitor 触发,internal-only | 同上 |
| 12 | Task 7.3 sse_manager.py | 订阅 Redis channel + 支持 last_event_id 补发(从 Redis Stream)+ tab 限制(每 session 最多 3 连接) | Batch 1 v2 §R4 / Batch 3 §B3-III |
| 13 | Task 7.3 `GET /sessions/{id}/stream?ticket=X&last_event_id=Y` | 改用 ticket + 支持 last_event_id | Batch 1 v2 §R4 |
| 14 | **Task 7.4 Part A 重大修订(CLI 子进程调度)** | 新增 ADR-066(subprocess 启动参数标准化)/ADR-067(coordinator_recovery 服务) | Master M3 / Batch 3 §A7-6 |
| 15 | Task 7.4 subprocess 启动 | 传 CALLBACK_URL / CALLBACK_SECRET / REDIS_URL / ENCRYPTION_KEY / PRISM_RUN_ID / PRISM_SESSION_ID / PRISM_USER_ID + 可选 OTEL_TRACE_ID | DOC-01 v4 §9.1 |
| 16 | Task 7.4 coordinator_recovery.py(新文件) | `POST /runs/{id}/resume` 调用:从 coordinator_plans 读 checkpoint → 重启子进程 → 传 `--resume-from-step=N` 参数 | Batch 2 §A4-3 / Master M3 |
| 17 | Task 7.4 alert_dispatcher.py(新文件) | 告警分发:audit_logs / SSE / IM / email 按 severity 分档 | Batch 5 §B5-IV |
| 18 | IM Webhook 幂等(属 DOC-08,此处引用) | session_service 创建 Run 前查 im_message_dedup 表 | Batch 3 B3-5 |
| 19 | 结构化日志 | run.started/completed/failed/crashed + callback.received/failed/dead_letter | 全局 §3.4 |
| 20 | Prometheus metrics | prism_runs_total / prism_run_duration_seconds / prism_agent_heartbeat_stale_total / prism_agent_subprocess_crashed_total | Batch 5 §B5-I |
| 21 | 所有 Part B 开头 | v4 Observability 采集说明 | 全局 |
| 22 | Redis namespace | perm_answer/perm_req/harness:heartbeat/sse:*/sse:*:stream 按 DOC-01 v4 §9.2 规范 | Batch 3 §B3-I |
| 23 | ADR 编号 | ADR-060~069 | 全局 |
| 24 | 交叉引用 | v3 → v4 | 全局 |
| 25 | 附录 A + 文末 | 修订清单 + 下一步 DOC-08 | SOP |

### 8.2 关键代码骨架

#### (A) sequence_no 原子性(Task 7.2)

```python
"""
Message sequence_no 并发原子性
方案 1:PostgreSQL per-session 序列(推荐)
方案 2:advisory lock + max+1(兼容性好)
"""

# 方案 1:使用 session_id 作为 sequence name
def get_next_sequence_no(session, session_id: str) -> int:
    """每个 session 一个独立序列"""
    seq_name = f"messages_seq_{session_id.replace('-', '_')}"
    # 首次调用时创建序列(IF NOT EXISTS 语义)
    session.execute(text(f"CREATE SEQUENCE IF NOT EXISTS {seq_name}"))
    result = session.execute(text(f"SELECT nextval('{seq_name}')"))
    return result.scalar()

# 方案 2:advisory lock
def get_next_sequence_no_lock(session, session_id: str) -> int:
    """用 session_id 的 bigint hash 作为 advisory lock key"""
    lock_key = int.from_bytes(session_id.replace('-', '')[:16].encode(), 'big') % (2**63)
    session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": lock_key})
    
    max_seq = session.execute(
        text("SELECT COALESCE(MAX(sequence_no), 0) FROM messages WHERE session_id = :sid"),
        {"sid": session_id}
    ).scalar()
    return max_seq + 1
    # commit 时锁自动释放
```

#### (B) HeartbeatMonitor(Task 7.3)

```python
"""
HeartbeatMonitor - 扫描僵尸 Run
每 10s 扫 `harness:heartbeat:*` Redis key,超 30s 无更新 → 标记 crashed
"""

import asyncio
import time
from app.services.run_lifecycle import RunLifecycleService

class HeartbeatMonitor:
    def __init__(
        self,
        redis_client,
        lifecycle: RunLifecycleService,
        scan_interval: int = 10,
        stale_threshold: int = 30,
    ):
        self._redis = redis_client
        self._lifecycle = lifecycle
        self._scan_interval = scan_interval
        self._stale_threshold = stale_threshold
        self._running = False
    
    async def run(self):
        """后台 task,在 FastAPI lifespan 中启动"""
        self._running = True
        while self._running:
            try:
                await self._scan_once()
            except Exception as e:
                logger.error("heartbeat.scan_failed", error=str(e), exc_info=True)
            
            await asyncio.sleep(self._scan_interval)
    
    async def _scan_once(self):
        """单次扫描"""
        cursor = 0
        now = int(time.time())
        
        while True:
            cursor, keys = await self._redis.scan(
                cursor=cursor,
                match="harness:heartbeat:*",
                count=100,
            )
            
            for key in keys:
                last_heartbeat = await self._redis.get(key)
                if last_heartbeat is None:
                    continue  # key 已过期(自然清理)
                
                age = now - int(last_heartbeat)
                if age > self._stale_threshold:
                    run_id = key.replace(b"harness:heartbeat:", b"").decode()
                    logger.warning(
                        "heartbeat.stale",
                        run_id=run_id,
                        age_seconds=age,
                    )
                    # 标记 Run crashed + promote 队列
                    await self._lifecycle.mark_crashed(
                        run_id=run_id,
                        reason=f"heartbeat_stale_{age}s",
                    )
                    await self._redis.delete(key)
                    
                    # Prometheus 计数
                    prism_agent_heartbeat_stale_total.inc()
                    prism_agent_subprocess_crashed_total.labels(reason="heartbeat").inc()
            
            if cursor == 0:
                break
    
    def stop(self):
        self._running = False
```

---

## 9. DOC-08 改写指令

**Backend IM Gateway** — 3 Task。

### 9.1 修订清单(12 处)

| # | 位置 | 修订内容 | 来源 |
|---|---|---|---|
| 1 | Header | 版本/日期/v4 摘要 | 全局 |
| 2 | Task 8.1 Part A | 新增 ADR-070(IM Webhook 幂等必做) | Batch 3 B3-5 |
| 3 | Task 8.1 im_dedup.py(新文件) | `is_duplicate(channel, msg_id) -> bool` + insert / 批量清理过期记录 | 同上 |
| 4 | Task 8.1 im_gateway.py | 入口先查幂等,命中则 ignore | 同上 |
| 5 | Task 8.1 可选:Redis 方案 | `SETNX im:dedup:{channel}:{msg_id} 1 EX 604800`(Phase 1 与 DB 二选一) | Batch 3 B3-5 |
| 6 | Task 8.2 Part A | 保留 3 个平台适配器,加结构化日志 | — |
| 7 | Task 8.3 Part A 修订 | im_bindings 唯一约束三元组 → 支持多群聊绑定 | Batch 3 §B3-IV |
| 8 | Task 8.3 pairing 逻辑 | platform_chat_id 不同 → 不同 binding 记录 | 同上 |
| 9 | 结构化日志 | im.message.received / im.message.duplicate / im.webhook.failed | 全局 §3.4 |
| 10 | Prometheus metrics | prism_im_messages_total / prism_im_webhook_duplicates_total | Batch 5 §B5-I |
| 11 | ADR 编号 | ADR-070~073 | 全局 |
| 12 | 附录 A + 文末 | 修订清单 + 下一步 DOC-09 | SOP |

---

## 10. DOC-09 改写指令

**Backend MCP-Provider-Admin** — 2-3 Task(含 v3.1 新 Task 9.3 Admin)。

### 10.1 修订清单(15 处)

| # | 位置 | 修订内容 | 来源 |
|---|---|---|---|
| 1 | Header | 版本/日期/v4 摘要 | 全局 |
| 2 | Task 9.1 Part A(MCP) | 无大改 | — |
| 3 | Task 9.2 Part A(Provider 配置 + 用量) | 新增 ADR-080(Provider scope 字段 CRUD)/ADR-081(capabilities 探测强制)/ADR-082(用量 API 返回 cache tokens 三字段) | Batch 3 §A9-3 |
| 4 | Task 9.2 provider_service | scope-aware CRUD(DOC-02 Task 2.3 引用的逻辑) | 同上 |
| 5 | Task 9.2 用量 API | `GET /providers/usage?period=day|week|month` 返回 input/output/cache_hit/cache_miss/cache_creation tokens + cost | Batch 1 v2 §R6 |
| 6 | Task 9.2 capability 探测 | `POST /providers/{id}/test` 返回 detected_capabilities(DOC-02 Task 2.3 引用) | Batch 3 §A9-3 |
| 7 | **Task 9.3 重大修订(Admin 审计)** — Part B 完整补全 | v3 Part B 缺失,v4 补完整实现 | Master M8 |
| 8 | Task 9.3 Part B 文件树 | admin.py + audit_service.py + admin_stats_service.py(系统统计) | Batch 3 C-1 |
| 9 | Task 9.3 审计日志查询 API | `GET /admin/audit-logs?action=...&user_id=...&start=...&end=...&page=...` 支持 Harness 事件筛选 | 同上 |
| 10 | Task 9.3 系统统计 API | `GET /admin/stats/dashboard` 返回 SystemStatsResponse(24h runs / 7d cost / harness events / 健康状态) | Batch 3 C-1 |
| 11 | Task 9.3 权限边界 | 禁止降级最后一个 admin / 禁止禁用自己 | Batch 3 C-1 |
| 12 | Task 9.3 用户管理 API | `GET /admin/users` / `PATCH /admin/users/{id}/role` | 同上 |
| 13 | Prometheus metrics | prism_provider_healthy / prism_provider_failover_total | Batch 5 §B5-I |
| 14 | ADR 编号 | ADR-080~085 | 全局 |
| 15 | 附录 A + 文末 | 修订清单 + 下一步 DOC-10 | SOP |

---

## 11. DOC-10 改写指令

**Frontend Foundation** — 3 Task。**最大规模扩充**(9KB → 50KB)。

### 11.1 修订清单(20 处)

| # | 位置 | 修订内容 | 来源 |
|---|---|---|---|
| 1 | Header | 版本/日期/v4 摘要 | 全局 |
| 2 | **DOC 开头新增前言** | 明确三份前端文档的关系:`UI design spec(2026-04-07)`=视觉真相源 / `DOC-10`=技术基建 / `DOC-11`=业务功能 + 冲突决议规则 | Batch 4 §B4-I / Master M6 |
| 3 | Task 10.1 Part A(Next.js 搭建) | 保留,加 v4 UI design spec 作为视觉真相源 | — |
| 4 | **Task 10.2 重大扩充(SSE 客户端)** | 从"几行简述" → 完整实现规范 | Batch 4 §B4-1 |
| 5 | Task 10.2 useSSE hook 状态机 | `idle → connecting → open → reconnecting → closed`(含重连指数退避) | Batch 4 §B4-4 |
| 6 | Task 10.2 ticket 换取流程 | `POST /auth/sse-ticket` → `new EventSource(?ticket=X&last_event_id=Y)` | Batch 1 v2 §R4 |
| 7 | Task 10.2 事件处理状态机 | text_delta merge / tool_use_delta 拼接 / message_complete 替换 streaming 消息的完整逻辑 | Batch 4 §B4-4 |
| 8 | Task 10.2 断线重连补发 | EventSource `lastEventId` + Backend 从 Redis Stream 补发 | Batch 1 v2 §R4 |
| 9 | **Task 10.3 重大扩充(API 客户端)** | 从"几行简述" → 完整实现规范(含错误处理 / 重试 / 401 自动跳转 / 404 处理 / 超时 / AbortController) | Batch 4 §B4-1 |
| 10 | Task 10.3 apiClient 完整代码 | 所有方法 + 错误边界 + 取消支持 + TanStack Query 集成 | 同上 |
| 11 | Task 10.3 错误上报 | `POST /api/v1/frontend-errors` 端点调用(DOC-12 Task 12.7) | Batch 5 §B5-I |
| 12 | Task 10.x 视觉系统 | 从 UI design spec 移植设计 tokens(色彩/字体/间距/阴影)到 Tailwind 配置 | UI design spec |
| 13 | Task 10.x 组件库 | ChatMessage / ToolCard / HarnessNotification / PermissionAskModal / 等基础组件骨架 | Batch 4 §B4-3 |
| 14 | Task 10.x permission_ask 弹窗 | PermissionAskModal 组件 + 订阅 SSE `permission_ask` 事件 + `POST /sessions/{id}/permission-answer` | Batch 3 B3-1 / Batch 2 §A3-7 |
| 15 | Task 10.x coordinator plan 可视化 | CoordinatorPlanPanel 组件 + 订阅 `coordinator_plan_update` 事件 | Batch 3 §A7-7 |
| 16 | Task 10.x 多 tab 限制 | SSE 连接拒绝时的前端提示 UI | Batch 3 §B3-III |
| 17 | 所有 Task Part B 开头 | v4 Observability:前端错误上报 + Web Vitals 上报 | Batch 5 §B5-I |
| 18 | ADR 编号 | ADR-090~095 | 全局 |
| 19 | 交叉引用 | v3 → v4 | 全局 |
| 20 | 附录 A + 文末 | 修订清单 + 下一步 DOC-11 | SOP |

### 11.2 关键代码骨架

#### (A) useSSE hook 状态机(Task 10.2)

```typescript
/**
 * useSSE - SSE 连接 React hook
 * 支持:ticket 换取 / 自动重连 / last_event_id 补发 / 状态机 / 事件分发
 */

import { useEffect, useRef, useState, useCallback } from 'react'

type SSEState = 'idle' | 'connecting' | 'open' | 'reconnecting' | 'closed'

interface UseSSEOptions {
  sessionId: string
  onTextDelta: (text: string, messageId: string) => void
  onToolUseDelta: (toolUseId: string, partialJson: string) => void
  onMessageComplete: (message: any) => void
  onHarnessEvent: (event: any) => void
  onPermissionAsk: (req: any) => void
  onCoordinatorPlanUpdate: (plan: any) => void
  onRunComplete: (summary: any) => void
  onRunError: (error: any) => void
  onRunCrashed: (crash: any) => void
}

export function useSSE(options: UseSSEOptions) {
  const [state, setState] = useState<SSEState>('idle')
  const esRef = useRef<EventSource | null>(null)
  const lastEventIdRef = useRef<string | null>(null)
  const reconnectAttempts = useRef(0)
  const reconnectTimerRef = useRef<NodeJS.Timeout | null>(null)
  
  const connect = useCallback(async () => {
    setState('connecting')
    
    try {
      // 1. 换取 ticket
      const ticketResp = await apiClient.post('/auth/sse-ticket', {
        session_id: options.sessionId,
      })
      const { ticket } = ticketResp.data
      
      // 2. 建立 EventSource
      const url = new URL(`/api/v1/sessions/${options.sessionId}/stream`, window.location.origin)
      url.searchParams.set('ticket', ticket)
      if (lastEventIdRef.current) {
        url.searchParams.set('last_event_id', lastEventIdRef.current)
      }
      
      const es = new EventSource(url.toString())
      esRef.current = es
      
      es.onopen = () => {
        setState('open')
        reconnectAttempts.current = 0
      }
      
      es.addEventListener('text_delta', (e: MessageEvent) => {
        lastEventIdRef.current = e.lastEventId
        const data = JSON.parse(e.data)
        options.onTextDelta(data.text, data.message_id)
      })
      
      es.addEventListener('tool_use_delta', (e: MessageEvent) => {
        lastEventIdRef.current = e.lastEventId
        const data = JSON.parse(e.data)
        options.onToolUseDelta(data.tool_use_id, data.partial_json)
      })
      
      es.addEventListener('message_complete', (e: MessageEvent) => {
        lastEventIdRef.current = e.lastEventId
        options.onMessageComplete(JSON.parse(e.data))
      })
      
      es.addEventListener('permission_ask', (e: MessageEvent) => {
        options.onPermissionAsk(JSON.parse(e.data))
      })
      
      es.addEventListener('coordinator_plan_update', (e: MessageEvent) => {
        options.onCoordinatorPlanUpdate(JSON.parse(e.data))
      })
      
      es.addEventListener('harness_event', (e: MessageEvent) => {
        options.onHarnessEvent(JSON.parse(e.data))
      })
      
      es.addEventListener('run_complete', (e: MessageEvent) => {
        options.onRunComplete(JSON.parse(e.data))
      })
      
      es.addEventListener('run_error', (e: MessageEvent) => {
        options.onRunError(JSON.parse(e.data))
      })
      
      es.addEventListener('run_crashed', (e: MessageEvent) => {
        options.onRunCrashed(JSON.parse(e.data))
      })
      
      es.onerror = () => {
        setState('reconnecting')
        es.close()
        esRef.current = null
        
        // 指数退避重连
        const delay = Math.min(1000 * 2 ** reconnectAttempts.current, 30000)
        reconnectAttempts.current++
        
        reconnectTimerRef.current = setTimeout(() => connect(), delay)
      }
      
    } catch (err) {
      console.error('SSE connect failed:', err)
      setState('closed')
    }
  }, [options])
  
  useEffect(() => {
    connect()
    return () => {
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
      esRef.current?.close()
      setState('closed')
    }
  }, [connect])
  
  return { state, reconnect: connect }
}
```

---

## 12. DOC-11 改写指令

**Frontend Features** — 5 Task + v3.1 新 Task 11.5(Skills Store)。

### 12.1 修订清单(22 处)

| # | 位置 | 修订内容 | 来源 |
|---|---|---|---|
| 1 | Header | 版本/日期/v4 摘要 | 全局 |
| 2 | **Task 11.1 扩充(Chat 界面)** | 加 permission_ask 弹窗 / coordinator plan 可视化 / run_crashed 恢复提示 | Batch 4 §B4-3 |
| 3 | Task 11.1 ChatHeader 双态 | 对齐 UI design spec §6 的双态布局 | Batch 4 §B4-I |
| 4 | **Task 11.2 扩充(Session 管理)** | 加 export/import / share / fork / archive / tag / 多选批量 | Batch 4 §C-1 |
| 5 | **Task 11.3 扩充(IM 绑定 UX)** | 配对码生成 → 发给 IM 机器人 → 等待绑定 → 显示成功的完整流程 | Batch 4 §C-1 |
| 6 | **Task 11.4 扩充(用量仪表盘)** | 加 Cache 命中率卡 + cache 节省金额 + 按 Provider 饼图 + 趋势折线 | Batch 4 §C-1 / Master M7 |
| 7 | **Task 11.5 大幅修订(Skills Store 拆分)** | 拆为 3 个子页:Skills Store / Plugin Builder / Harness Config | Master M8 / Batch 4 §C-1 |
| 8 | Task 11.5 Skills Store | 搜索栏(支持 source filter)/ Skill 列表卡片 / 详情页 / 安装/卸载按钮 | 同上 |
| 9 | Task 11.5 Plugin Builder | 对话式 UI + 实时完整度进度条 + 右侧 PluginStructureTree 实时预览 | Batch 4 §C-1 |
| 10 | Task 11.5 Harness Config | 只读展示(DB 层 + 默认层)+ source_trace 显示字段来自哪一源 | Master M8 |
| 11 | **新增 Task 11.6(Admin Obs 面板)** | 从 DOC-11 独立出来,专职消费 DOC-12 的 API | Batch 5 §B5-II |
| 12 | Task 11.6 Harness Analytics 面板 | 汇总卡 + 信号分布 + runs 列表 + harness_summary 详情 | Batch 5 §B5-I |
| 13 | Task 11.6 Entropy Alerts 面板 | 告警列表 / 过滤 / 确认 / 历史 | Batch 5 §B5-IV |
| 14 | Task 11.6 Grafana 链接 | 外链到 localhost:3001(docker-compose.monitoring.yml 启动后) | Batch 5 §B5-V |
| 15 | 所有 Task 组件实现 | 扩充 Part B 实现规范(当前部分 Task 只有几行) | Batch 4 §B4-1 |
| 16 | Playwright E2E 测试 | 每个 Task 必带 desktop + mobile 双视口 E2E 脚本样例 | UI design spec / Batch 4 §B4-V |
| 17 | Poco 功能保留 vs 体积 | 明文说明:参考 Poco 68 文件架构完整保留功能,但不 fork 代码(体积 <10MB) | Batch 4 §B4-5 |
| 18 | 结构化日志/错误上报 | 前端关键操作 → `POST /frontend-errors` | Batch 5 §B5-I |
| 19 | ADR 编号 | ADR-100~108 | 全局 |
| 20 | 交叉引用 | v3 → v4 | 全局 |
| 21 | Observability 采集说明 | 加 Web Vitals / 首 token 延迟 / Cache 命中率前端埋点 | Batch 5 §B5-I |
| 22 | 附录 A + 文末 | 修订清单 + 下一步 DOC-12 | SOP |

---

## 13. DOC-12 改写指令

**Observability & Entropy** — **最大扩充**(3 Task → 7 Task,27KB → 80KB)。

### 13.1 修订清单(28 处)

| # | 位置 | 修订内容 | 来源 |
|---|---|---|---|
| 1 | Header | 版本 3.1 → 4.0,Task 数 3 → 7 | 全局 + Batch 5 §B5-I |
| 2 | Task 12.1 Part A | ADR-110(精确 tokenizer 直接上)/ADR-111(ResourceMonitor 按百分比而非绝对值) | Batch 5 §A12-1 §A12-2 |
| 3 | Task 12.1 TokenEstimator | 重构:CalibratingCharCountEstimator(有 usage feedback 时动态校准系数)+ AnthropicTokenCounter + TiktokenEstimator | Batch 5 §A12-1 |
| 4 | Task 12.1 ResourceMonitor | 按百分比阈值(70/85)+ 绝对值 fallback + CPU + 子进程数 + 队列深度 | Batch 5 §A12-2 |
| 5 | Task 12.2 Part A | ADR-112(Entropy 信号从 5 扩到 8)/ADR-113(阈值自动校准) | Batch 5 §A12-3 §A12-4 §A12-5 |
| 6 | Task 12.2 HarnessAnalytics.aggregate() | 返回结构加 cache_stats(hit_tokens / miss_tokens / creation_tokens / hit_ratio / creation_cost_ratio / by_provider) | Batch 5 §A12-3 |
| 7 | Task 12.2 EntropyDetector 8 信号 | 原 5 个 + Provider 健康度下降 + Cache 命中率下降 + permission_ask 超时率上升 | Batch 5 §A12-4 |
| 8 | Task 12.2 ThresholdCalibrator(新) | 每周扫 30 天 harness_summary,p90 校准阈值,平滑过渡 0.7*current + 0.3*p90 | Batch 5 §A12-5 |
| 9 | Task 12.3 Part A | ADR-114(liveness/readiness/detailed 分离)/ADR-115(Docker Compose 全部资源限制) | Batch 5 §A12-6 §A12-7 |
| 10 | Task 12.3 /health 拆分 | /health/live(200 进程活)/ /health/ready(503 若任何依赖 critical)/ /health/detailed(admin only) | Batch 5 §A12-6 |
| 11 | Task 12.3 Docker Compose | backend/postgres/redis/nginx 每个都有 limits + reservations + healthcheck | Batch 5 §A12-7 |
| 12 | Task 12.3 nginx.conf SSE 透传 | X-Accel-Buffering: no + proxy_read_timeout 3600s | — |
| 13 | **新 Task 12.4(Prometheus Metrics)** | 完整 metrics 定义(见 §13.2 代码骨架)+ /metrics 端点 | Batch 5 §B5-I |
| 14 | Task 12.4 metrics 覆盖面 | Run 级 + TAOR 级 + 工具级 + Harness 级 + Model 级 + Permission 级 + Session 级 + Provider 级 + IM 级 + 子进程级 | 同上 |
| 15 | Task 12.4 Grafana Dashboard | 配置 4 套 dashboard JSON 文件 + docker-compose.monitoring.yml 开箱 | Batch 5 §B5-V |
| 16 | Task 12.4 provisioning | Grafana auto-load dashboards + datasource | Batch 5 §B5-V |
| 17 | **新 Task 12.5(OTel Tracing)** | 初始化 TracerProvider + OTLP/Stdout exporter + 核心 span 树结构(run/taor_turn/prompt_assembly/model_request/tool_use/middleware_chain) | Batch 5 §B5-I |
| 18 | Task 12.5 跨进程 trace | Backend 子进程启动时传 OTEL_TRACE_ID 环境变量 + W3C TraceContext 头 | 同上 |
| 19 | Task 12.5 关键 trace 标签 | run.id/session.id/user.id/agent.type/route.mode/tool.name/provider.name/model.id/harness.guardrail_triggered | 同上 |
| 20 | **新 Task 12.6(结构化日志)** | structlog 配置 + contextvars 自动绑定 + JSON 输出 + 日志级别规范 + 事件名约定 | Batch 5 §B5-I |
| 21 | **新 Task 12.7(前端错误上报)** | `POST /frontend-errors` 端点 + FrontendErrorPayload schema + 写 audit_logs | Batch 5 §B5-I / Batch 4 §B4-I |
| 22 | Task 12.7 Prometheus metric | prism_frontend_errors_total by severity/viewport | 同上 |
| 23 | **新 Task 12.8(告警通道 AlertDispatcher)** | audit/SSE/IM/email 按 severity 分档分发 | Batch 5 §B5-IV |
| 24 | Task 12.8 IM 告警 | 复用 DOC-08 IM Gateway,admin 在 settings 配置"critical 告警发到 X 群" | 同上 |
| 25 | 所有 Task Part B | v4 Observability 自引用 | 全局 |
| 26 | ADR 编号 | ADR-110~120 | 全局 |
| 27 | 目录 | 3 项 → 8 项 | Batch 5 §B5-I |
| 28 | 附录 A + 文末 | 修订清单 + "全部文档完成" | SOP |

### 13.2 Prometheus Metrics 完整定义(Task 12.4)

**直接把 `review-batch5.md` §B5-I 的 60+ 指标代码块完整复制到 DOC-12 v4 Task 12.4**。位置:`/home/claude/review-batch5.md` 或 `/mnt/user-data/outputs/review-batch5.md`。

### 13.3 Grafana Dashboard JSON 模板要求

Task 12.4 必须交付 4 个 dashboard JSON 文件:

- `monitoring/grafana/dashboards/prism-overview.json` — Runs/s, Errors/s, P95 latency, 活跃 Session 数
- `monitoring/grafana/dashboards/prism-harness.json` — guardrail / permission / hook 事件时序
- `monitoring/grafana/dashboards/prism-models.json` — tokens / cost / cache / provider health
- `monitoring/grafana/dashboards/prism-agents.json` — 子进程 / fork / background 生命周期

每个 JSON 文件放在 PRD 的附录或独立文件中。格式参考 Grafana export 标准。

---

## 14. DOC-CC-ONBOARDING 新建指令

**最后一份交付,全新文档**。已在 `review-master.md` §4.2 给出完整大纲(13 节)。

### 14.1 完整大纲(已确认)

```
§0 如何阅读本文档
§1 项目心智模型(3 分钟速成)
§2 必读前置(5 份文件的阅读顺序)
§3 开发六原则(硬底线)
§4 Task 执行标准流程(9 步验收)
§5 Skill 加载规则
§6 关键架构心法(从 CC 学到的 7 条)
§7 三个参考锚点的差异化吸收(Manus + CC + 主权工具)
§8 常见陷阱与反模式(10 条,对应 review-master §6.4)
§9 断点恢复协议
§10 质量自检 Checklist(引用 review-master §3.4)
§11 你(Sonnet 4.6)的工作边界
§12 CC 源码关键文件索引(引用 review-patch-pdf.md 附录)
§13 三层质量保证
```

### 14.2 关键陷阱清单(§8,必须列全 10 条)

| # | 陷阱 | 反模式 | 正解 |
|---|---|---|---|
| 8.1 | 回调风暴 | 每个 token 发 HTTP | Redis PUBLISH,Backend 订阅 forward |
| 8.2 | Compaction 破坏 tool_use↔tool_result 配对 | 按 index 裁剪 messages | 按回合组为原子单元裁剪 |
| 8.3 | 工具调用串行化 | for 循环 await | asyncio.gather 并行(无依赖时) |
| 8.4 | SSE JWT 走 URL query | token 泄露到日志/history/referer | 一次性 ticket(60s 过期,用后即焚) |
| 8.5 | 每个服务一个 Harness 实例 | Backend + 子进程都跑 Harness | 只在子进程跑,Backend 不持有 |
| 8.6 | sequence_no 用 max+1 | 并发 insert 时冲突 | PostgreSQL per-session 序列 or advisory_xact_lock |
| 8.7 | JWT_SECRET 当 ENCRYPTION_KEY 用 | 轮换 JWT 时 Provider key 全丢 | 三密钥独立 + 启动校验 |
| 8.8 | ask 权限用轮询 | 浪费连接,延迟高 | Redis BLPOP 阻塞等待 |
| 8.9 | Fork 子 Agent 覆盖 model | Cache miss | Fork 三条 prompt-level 约束强制 |
| 8.10 | PluginBuilder 硬编码 5 轮 | 有人 2 轮就够了,有人 8 轮还不够 | 完整度打分动态决定 |

### 14.3 CC 源码关键文件索引(§12)

引用 `review-patch-pdf.md` 附录的 11 个关键文件清单。

### 14.4 预期产出

- 文件:`DOC-CC-ONBOARDING.md`
- 预计字数:6000-8000 字
- 预计行数:~600 行
- 预计大小:~25KB

---

## 15. 完工交付清单

改写阶段全部结束后,`/mnt/user-data/outputs/` 应包含:

### 必交付(16 份文档)

1. `DOC-00-v4.md` ✅(已完成)
2. `DOC-01-v4.md` ✅(已完成)
3. `DOC-02-v4.md` ✅(已完成)
4. `DOC-03-v4.md`
5. `DOC-04-v4.md`
6. `DOC-05-v4.md`
7. `DOC-06-v4.md`
8. `DOC-07-v4.md`
9. `DOC-08-v4.md`
10. `DOC-09-v4.md`
11. `DOC-10-v4.md`
12. `DOC-11-v4.md`
13. `DOC-12-v4.md`
14. `DOC-CC-ONBOARDING.md`

### 支持文档

15. `changes-checklist.md` — 115 个修改点的落地状态表(从本文档 §4-13 汇总)
16. `cross-references.md` — 跨文档引用清单
17. `adr-index.md` — 所有 ADR 编号汇总(ADR-001 ~ ADR-120)
18. `api-routes-index.md` — 所有 API 路由汇总
19. `monitoring/grafana/dashboards/prism-overview.json`
20. `monitoring/grafana/dashboards/prism-harness.json`
21. `monitoring/grafana/dashboards/prism-models.json`
22. `monitoring/grafana/dashboards/prism-agents.json`

### 总规模预估

- 文档合计:~1MB Markdown,约 24 万字
- Grafana dashboards:~50KB JSON

---

## 16. 最后提醒给 Claude Code

**三条最重要的**:

1. **改不是重写** — 99% 照搬原文,只动 review 发现的具体位置。不要自作主张添加 review 没提的东西。

2. **密度达标** — Sonnet 4.6 是下一个执行者,他看完 PRD 要能零猜测地开写。所有 `...` / `TODO` / 模糊表述必须具象化。代码骨架要能直接 copy-paste。

3. **铁律 6 "禁止打补丁"** — 改 PRD 时也适用。如果你发现某个 review 点的修改,需要动到原文档没涉及的架构,**停下来写一份 blocker.md 给用户**,不要擅自扩大改动。

祝开工顺利。

---

> **本文档版本**: 1.0 final
> **来源**: Claude Opus 4.7 Web
> **预计 Claude Code 完成时间**: 单 session 全部改完,1M context 应该装得下
> **下一步**: Claude Code 按 §2 SOP 逐份改写,按 §15 落盘
