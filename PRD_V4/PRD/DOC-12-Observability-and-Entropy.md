# Prism 棱镜 v2 — Observability & Entropy (DOC-12)

> **文档编号**: DOC-12  
> **版本**: 3.1  
> **日期**: 2026-04-02  
> **性质**: 实现文档 — 可观测性体系、熵管理、运维监控  
> **前置依赖**: DOC-03 v3（Harness Runtime）, DOC-07（harness_summary schema）, DOC-01 v3（服务拓扑 + 部署配置）  
> **Phase**: 4（运维封装）  
> **Task 数**: 3  
> **审计关注点**:  
> - **内存用量监控（2C2G 约束）**：总空闲 ~340MB，Agent 子进程需要在剩余内存中运行。必须监控 Backend 进程和子进程的内存占用，接近阈值时告警  
> - **路由决策准确率追踪**：DOC-04 Task 4.4 的 TaskRouter 使用关键词匹配，需要追踪路由准确率（用户手动覆盖 agent_type 的比例 = 路由不准确的信号）  
> - **TokenEstimator 接口**：DOC-02 Task 2.4 的 `ContextBudgetManager.estimate_tokens()` 使用粗略字符计数，需要提供可替换的精确计算接口（tiktoken / tokenizers 库）  
> - **harness_summary 消费与展示**：DOC-07 定义了 harness_summary JSONB schema，本文档定义如何聚合、分析和展示这些数据

---

## 目录

1. [Task 12.1: TokenEstimator 接口与资源监控](#task-121-tokenestimator-接口与资源监控)
2. [Task 12.2: Harness 数据聚合与 Entropy Detection](#task-122-harness-数据聚合与-entropy-detection)
3. [Task 12.3: 运维配置与健康检查增强](#task-123-运维配置与健康检查增强)

---

## Task 12.1: TokenEstimator 接口与资源监控

### Part A — 设计与解释

#### 问题陈述

DOC-02 Task 2.4 的 `ContextBudgetManager.estimate_tokens()` 使用粗略的字符计数（1 token ≈ 4 英文字符 / 1.5 中文字符），误差在 20-30%。这对 Compaction 的阈值判断影响较大——可能过早触发（浪费上下文空间）或过晚触发（API 报错）。

需要一个可替换的 `TokenEstimator` 接口，Phase 1 使用字符计数（零依赖，ms 级），Phase 2 可切换到 tiktoken/tokenizers（精确但需要额外依赖）。

同时，Prism 运行在 2C2G 的资源约束下，需要监控内存用量并在接近阈值时告警。

#### 设计决策

- **ADR-031**: TokenEstimator 策略模式
  - 接口：`estimate(text: str) -> int`
  - 实现 1：`CharCountEstimator`（默认，零依赖）
  - 实现 2：`TiktokenEstimator`（精确，需要 `tiktoken` 库）
  - 通过 config 配置选择：`TOKEN_ESTIMATOR=charcount | tiktoken`
  - `ContextBudgetManager` 依赖注入 `TokenEstimator`，不直接使用字符计数

> **局限性说明**：TiktokenEstimator 基于 OpenAI 的 tiktoken 库，对 Claude 模型的 token 计数存在约 5-15% 的偏差。这是已知局限，Phase 1 可接受。Phase 2 可通过接入 Anthropic 的 token counting API 提升精度。

#### 验收标准

- TokenEstimator 接口定义清晰，两个实现可互换
- ContextBudgetManager 重构为依赖注入 TokenEstimator
- 内存监控能获取 Backend 进程和子进程的 RSS
- 内存超过阈值（如 1.5GB）时通过回调告警
- 路由决策准确率可查询（从 runs 表统计 agent_type override 比例）

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在构建 Prism v2 的 Token 估算接口和资源监控。

请先加载以下 Skill（如果找不到任何一个，立即停止并告知我）：
- using-superpowers

## 前置条件

DOC-02 Task 2.4（ContextBudgetManager）和 DOC-04 Task 4.4（TaskRouter）已完成

## 要创建/修改的文件

```
executor/engine/
├── token_estimator.py         # TokenEstimator 接口 + 两个实现
└── context_budget.py          # 修改：依赖注入 TokenEstimator

backend/app/services/
├── resource_monitor.py        # 内存/CPU 监控
└── route_analytics.py         # 路由决策准确率分析
```

## 实现规范

### 1. executor/engine/token_estimator.py

```python
"""
TokenEstimator — 可替换的 Token 计数策略

策略模式：ContextBudgetManager 依赖注入此接口，
不直接使用字符计数。

Phase 1 默认 CharCountEstimator（零依赖）。
Phase 2 可切换 TiktokenEstimator（精确）。
"""

from abc import ABC, abstractmethod

class TokenEstimator(ABC):
    @abstractmethod
    def estimate(self, text: str) -> int:
        """估算文本的 token 数"""
        ...
    
    @abstractmethod
    def estimate_messages(self, messages: list[dict]) -> int:
        """估算消息列表的 token 数（含 role/structure overhead）"""
        ...

class CharCountEstimator(TokenEstimator):
    """
    基于字符计数的粗略估算。
    
    规则：
    - ASCII 字符：4 字符 ≈ 1 token
    - CJK 字符：1.5 字符 ≈ 1 token
    - 消息结构开销：每条消息 +4 token（role + format）
    
    误差范围：±20-30%
    优势：零依赖，< 1ms
    """
    
    def estimate(self, text: str) -> int:
        cjk_count = sum(1 for c in text if '\u4e00' <= c <= '\u9fff' or '\u3000' <= c <= '\u303f')
        ascii_count = len(text) - cjk_count
        return int(ascii_count / 4 + cjk_count / 1.5)
    
    def estimate_messages(self, messages: list[dict]) -> int:
        total = 0
        for msg in messages:
            total += 4  # role + structure overhead
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.estimate(content)
            elif isinstance(content, list):
                for block in content:
                    total += self.estimate(str(block))
        return total

class TiktokenEstimator(TokenEstimator):
    """
    基于 tiktoken 的精确计算。
    
    需要安装：pip install tiktoken
    使用 cl100k_base encoding（Claude / GPT-4 的近似编码器）。
    
    误差范围：< 5%（不同模型的 tokenizer 略有差异）
    劣势：首次加载需要下载编码器文件（~1MB）
    """
    
    def __init__(self, model: str = "cl100k_base"):
        import tiktoken
        self._enc = tiktoken.get_encoding(model)
    
    def estimate(self, text: str) -> int:
        return len(self._enc.encode(text))
    
    def estimate_messages(self, messages: list[dict]) -> int:
        total = 0
        for msg in messages:
            total += 4
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.estimate(content)
            elif isinstance(content, list):
                for block in content:
                    total += self.estimate(str(block))
        return total

def create_estimator(strategy: str = "charcount") -> TokenEstimator:
    """工厂函数"""
    if strategy == "tiktoken":
        return TiktokenEstimator()
    return CharCountEstimator()
```

### 2. executor/engine/context_budget.py 修改

将所有 `self.estimate_tokens()` 内部的字符计数逻辑替换为 `self._estimator.estimate()` 调用：

```python
class ContextBudgetManager:
    def __init__(
        self,
        max_context_tokens: int = 128000,
        reserve_for_response: int = 4096,
        tool_result_max_chars: int = 10000,
        estimator: TokenEstimator | None = None,    # ← 新增
    ):
        self._estimator = estimator or CharCountEstimator()
        ...
    
    def estimate_tokens(self, text: str) -> int:
        return self._estimator.estimate(text)
```

### 3. backend/app/services/resource_monitor.py

```python
"""
资源监控 — 内存/CPU 使用率追踪

2C2G 约束下的监控策略：
- 每 30 秒采样一次
- Backend 进程 RSS > 500MB → warning
- 总系统内存使用 > 1.5GB → critical
- 子进程数量追踪
"""

import psutil
import os

class ResourceMonitor:
    WARNING_THRESHOLD_MB = 500      # Backend 进程 RSS 告警阈值
    CRITICAL_THRESHOLD_MB = 1500    # 系统总内存告警阈值
    
    def get_backend_memory_mb(self) -> float:
        """Backend 进程的 RSS (MB)"""
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / (1024 * 1024)
    
    def get_system_memory_usage(self) -> dict:
        """系统内存使用情况"""
        mem = psutil.virtual_memory()
        return {
            "total_mb": mem.total / (1024 * 1024),
            "used_mb": mem.used / (1024 * 1024),
            "available_mb": mem.available / (1024 * 1024),
            "percent": mem.percent,
        }
    
    def get_child_processes(self) -> list[dict]:
        """获取 Backend 的子进程列表（Agent 执行器）"""
        parent = psutil.Process(os.getpid())
        children = parent.children(recursive=True)
        return [
            {
                "pid": c.pid,
                "name": c.name(),
                "memory_mb": c.memory_info().rss / (1024 * 1024),
                "cpu_percent": c.cpu_percent(),
                "status": c.status(),
            }
            for c in children
        ]
    
    def check_health(self) -> dict:
        """
        综合健康检查。
        
        返回:
        {
            "status": "ok" | "warning" | "critical",
            "backend_memory_mb": 200,
            "system_memory": {...},
            "child_count": 2,
            "warnings": ["Backend RSS exceeds 500MB"],
        }
        """
        backend_mem = self.get_backend_memory_mb()
        sys_mem = self.get_system_memory_usage()
        children = self.get_child_processes()
        
        warnings = []
        status = "ok"
        
        if backend_mem > self.WARNING_THRESHOLD_MB:
            warnings.append(f"Backend RSS: {backend_mem:.0f}MB > {self.WARNING_THRESHOLD_MB}MB")
            status = "warning"
        
        if sys_mem["used_mb"] > self.CRITICAL_THRESHOLD_MB:
            warnings.append(f"System memory: {sys_mem['used_mb']:.0f}MB > {self.CRITICAL_THRESHOLD_MB}MB")
            status = "critical"
        
        return {
            "status": status,
            "backend_memory_mb": round(backend_mem, 1),
            "system_memory": sys_mem,
            "child_count": len(children),
            "children": children,
            "warnings": warnings,
        }
```

### 4. backend/app/services/route_analytics.py

```python
"""
路由决策准确率分析

追踪指标：用户手动覆盖 agent_type 的比例。
如果用户频繁手动指定 agent_type（而非让 TaskRouter 自动选择），
说明自动路由不够准确。

数据来源：
- runs.harness_summary.route_mode / route_agent_type / route_reason
- 如果 route_reason 包含 "显式指定" → 用户覆盖
- 如果 route_reason 包含 "关键词匹配" 或 "默认路由" → 自动路由
"""

class RouteAnalytics:
    def __init__(self, db: Session):
        self._db = db
    
    def get_accuracy_stats(self, days: int = 30) -> dict:
        """
        统计最近 N 天的路由准确率。
        
        返回:
        {
            "total_runs": 100,
            "auto_routed": 85,        # 自动路由次数
            "user_overridden": 15,     # 用户手动覆盖次数
            "auto_route_rate": 0.85,   # 自动路由率（越高越好）
            "override_breakdown": {    # 按 agent_type 的覆盖分布
                "research": 8,
                "verifier": 5,
                "planner": 2,
            },
        }
        """
        # 从 runs 表查询 harness_summary JSONB
        # 按 route_reason 分类统计
        ...
```

## 验证步骤

```bash
# 1. 编译检查
docker compose -f docker-compose.dev.yml exec backend python -m py_compile executor/engine/token_estimator.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/services/resource_monitor.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/services/route_analytics.py

# 2. TokenEstimator 测试
docker compose -f docker-compose.dev.yml exec backend python -c "
from executor.engine.token_estimator import CharCountEstimator, create_estimator

e = CharCountEstimator()
# 英文
assert abs(e.estimate('Hello, world!') - 3) <= 2
# 中文
assert abs(e.estimate('你好世界') - 3) <= 2
# 混合
mixed = 'Hello 你好 World 世界'
tokens = e.estimate(mixed)
assert tokens > 0
print(f'Mixed text tokens: {tokens}')

# 工厂
e2 = create_estimator('charcount')
assert isinstance(e2, CharCountEstimator)
print('TokenEstimator: PASS')
"

# 3. 资源监控测试
docker compose -f docker-compose.dev.yml exec backend python -c "
from app.services.resource_monitor import ResourceMonitor

monitor = ResourceMonitor()
health = monitor.check_health()
print(f'Status: {health[\"status\"]}')
print(f'Backend memory: {health[\"backend_memory_mb\"]}MB')
print(f'System memory: {health[\"system_memory\"][\"percent\"]}%')
print(f'Child processes: {health[\"child_count\"]}')
assert health['status'] in ('ok', 'warning', 'critical')
print('ResourceMonitor: PASS')
"
```

## 完成后

1. 更新 PROGRESS.md
2. 更新 DECISIONS.md：记录 ADR-031（TokenEstimator 策略模式）
3. 在 requirements.txt 中加入 `psutil>=5.9.0`（资源监控），`tiktoken>=0.7.0`（可选）
4. 加载 Simplify skill 审查
5. 加载 PJR skill 验证
6. `git add -A && git commit -m "feat: TokenEstimator interface + resource monitor + route analytics"`
```

---

## Task 12.2: Harness 数据聚合与 Entropy Detection

### Part A — 设计与解释

#### 问题陈述

DOC-07 定义了 `runs.harness_summary` JSONB 的完整 schema。本 Task 实现对这些数据的聚合分析和 Entropy Detection（熵漂移检测）。

Entropy 是指 Agent 输出质量随时间退化的现象——格式漂移、指令遵循率下降、工具调用模式异常。OpenAI Codex 团队每周花 20% 时间清理 AI slop，Prism 将这个过程系统化为检测 + 告警 + 人工触发清理。

#### Entropy 检测信号

| 信号 | 来源 | 阈值 | 含义 |
|------|------|------|------|
| 护栏触发率上升 | harness_summary.guardrail_triggers / turn_count | > 0.3 | Agent 越来越频繁触碰护栏 |
| 工具错误率上升 | harness_summary.total_tool_errors / total_tool_calls | > 0.2 | 工具调用质量下降 |
| Compaction 频率上升 | compaction_events 数量 / turn_count | > 0.2 | 上下文管理压力增大 |
| 循环检测命中 | loop_detections > 0 | > 0 | Agent 陷入重复模式 |
| 平均 turn_count 上升 | 近 7 天 vs 前 7 天的平均 turn_count | 增长 > 50% | 任务完成效率下降 |

#### Entropy Detection 模式（Phase 1：半自动）

1. **检测**：定时分析 harness_summary 数据，计算上述信号
2. **告警**：超过阈值时写入 audit_logs（action: `harness.entropy_alert`）+ 可选通知 Admin
3. **人工触发清理**：Admin 查看告警后决定是否需要调整 Prompt / 护栏规则 / 工具配置

不做全自动规则生成（P7 可撕裂原则——避免"修复 AI 输出的 AI"引入新的不确定性）。

> **窗口修复 (P0)**：`HarnessAnalytics.aggregate()` 增加 `offset_days: int = 0` 参数。EntropyDetector 使用非重叠窗口：
> ```python
> current = analytics.aggregate(days=7, offset_days=0)   # 最近 7 天
> previous = analytics.aggregate(days=7, offset_days=7)   # 7~14 天前
> ```
> 两个窗口不重叠，delta 计算才有意义。

#### 验收标准

- HarnessSummaryAggregator 能聚合最近 N 天的 harness_summary 数据
- Entropy Detection 能计算 5 个信号指标
- 超过阈值时生成告警记录
- 提供查询接口供 Admin 面板展示
- 定时任务（或手动触发）执行检测

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在构建 Prism v2 的 Entropy Detection 系统。DOC-07 的 harness_summary schema 已定义。

请先加载以下 Skill（如果找不到任何一个，立即停止并告知我）：
- using-superpowers

## 前置条件

DOC-07 完成，runs.harness_summary 字段已有数据写入

## 要创建的文件

```
backend/app/services/
├── harness_analytics.py       # harness_summary 数据聚合
└── entropy_detector.py        # Entropy Detection
```

## 实现规范

### 1. app/services/harness_analytics.py

```python
"""
Harness Summary 数据聚合

消费 runs.harness_summary JSONB，提供多维度统计。
schema 定义见 DOC-07 前置定义。
对缺失字段用默认值兜底（get + default），不假设所有字段存在。
"""

class HarnessAnalytics:
    def __init__(self, db: Session):
        self._db = db
    
    def aggregate(self, user_id: str | None = None, days: int = 7) -> dict:
        """
        聚合最近 N 天的 Harness 数据。
        
        user_id=None 时聚合全局（Admin 用）。
        
        返回:
        {
            "period": {"start": "...", "end": "...", "days": 7},
            "runs_analyzed": 42,
            "totals": {
                "turns": 500,
                "tool_calls": 300,
                "tool_errors": 15,
                "guardrail_triggers": 8,
                "permission_denials": 3,
                "compaction_events": 12,
                "loop_detections": 1,
                "forks": 5,
            },
            "averages": {
                "turns_per_run": 11.9,
                "tool_calls_per_run": 7.1,
                "error_rate": 0.05,           # tool_errors / tool_calls
                "guardrail_rate": 0.016,       # guardrail_triggers / turns
                "compaction_rate": 0.024,      # compaction_events / turns
            },
            "route_distribution": {
                "direct": 35,
                "coordinator": 7,
                "agent_types": {"general": 30, "research": 8, "verifier": 4},
            },
            "peak_context_usage": {
                "max": 0.92,
                "avg": 0.65,
                "p95": 0.85,
            },
        }
        """
        # 从 runs 表查询最近 N 天的 completed/failed runs
        # 解析每条的 harness_summary JSONB
        # 用 get() + 默认值防御缺失字段
        ...
```

### 2. app/services/entropy_detector.py

```python
"""
Entropy Detection — 熵漂移检测

Phase 1：半自动模式（检测 + 告警 + 人工触发清理）

检测周期：每天一次（或手动触发）
对比窗口：最近 7 天 vs 前 7 天
告警写入：audit_logs (action: harness.entropy_alert)
"""

class EntropyDetector:
    # 告警阈值
    GUARDRAIL_RATE_THRESHOLD = 0.3        # 护栏触发率
    TOOL_ERROR_RATE_THRESHOLD = 0.2       # 工具错误率
    COMPACTION_RATE_THRESHOLD = 0.2       # Compaction 频率
    TURN_COUNT_GROWTH_THRESHOLD = 0.5     # 平均 turn_count 增长率

    > **阈值校准说明**：以下阈值为初始估计值，通过环境变量可配置（`ENTROPY_THRESHOLD_*`），上线后根据实际数据校准。

    def __init__(self, db: Session, analytics: HarnessAnalytics):
        self._db = db
        self._analytics = analytics
    
    def detect(self, user_id: str | None = None) -> list[dict]:
        """
        执行 Entropy 检测。

        返回告警列表（可能为空）。
        每个告警写入 audit_logs。

        返回:
        [
            {
                "signal": "guardrail_rate",
                "current_value": 0.35,
                "threshold": 0.3,
                "severity": "warning",
                "message": "护栏触发率 35% 超过阈值 30%",
            },
            ...
        ]
        """
        current = self._analytics.aggregate(user_id=user_id, days=7, offset_days=0)
        previous = self._analytics.aggregate(user_id=user_id, days=7, offset_days=7)
        # 使用非重叠窗口：current 是最近 7 天，previous 是 7-14 天前
        
        alerts = []
        
        # 1. 护栏触发率
        gr_rate = current["averages"]["guardrail_rate"]
        if gr_rate > self.GUARDRAIL_RATE_THRESHOLD:
            alerts.append(self._make_alert("guardrail_rate", gr_rate, self.GUARDRAIL_RATE_THRESHOLD, "护栏触发率偏高"))
        
        # 2. 工具错误率
        err_rate = current["averages"]["error_rate"]
        if err_rate > self.TOOL_ERROR_RATE_THRESHOLD:
            alerts.append(self._make_alert("tool_error_rate", err_rate, self.TOOL_ERROR_RATE_THRESHOLD, "工具错误率偏高"))
        
        # 3. Compaction 频率
        comp_rate = current["averages"]["compaction_rate"]
        if comp_rate > self.COMPACTION_RATE_THRESHOLD:
            alerts.append(self._make_alert("compaction_rate", comp_rate, self.COMPACTION_RATE_THRESHOLD, "上下文压缩频率偏高"))
        
        # 4. 循环检测命中
        if current["totals"]["loop_detections"] > 0:
            alerts.append(self._make_alert("loop_detection", current["totals"]["loop_detections"], 0, "存在循环检测命中"))
        
        # 5. turn_count 增长
        if previous["runs_analyzed"] > 0:
            current_avg = current["averages"]["turns_per_run"]
            previous_avg = previous["averages"]["turns_per_run"]
            if previous_avg > 0:
                growth = (current_avg - previous_avg) / previous_avg
                if growth > self.TURN_COUNT_GROWTH_THRESHOLD:
                    alerts.append(self._make_alert(
                        "turn_count_growth", growth, self.TURN_COUNT_GROWTH_THRESHOLD,
                        f"平均循环次数增长 {growth*100:.0f}%（{previous_avg:.1f} → {current_avg:.1f}）"
                    ))
        
        # 写入 audit_logs
        for alert in alerts:
            from app.models.audit import AuditLog
            log = AuditLog(
                action="harness.entropy_alert",
                resource_type="system",
                details=alert,
            )
            self._db.add(log)
        
        if alerts:
            self._db.commit()
        
        return alerts
    
    def _make_alert(self, signal: str, value, threshold, message: str) -> dict:
        return {
            "signal": signal,
            "current_value": value,
            "threshold": threshold,
            "severity": "warning",
            "message": message,
        }
```

### 3. API 端点

在 `app/api/v1/harness.py` 中新增（DOC-01 v3 §6.10 已预留）：

```python
@router.get("/harness/analytics", response_model=ApiResponse[dict])
def get_harness_analytics(
    days: int = 7,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Harness 数据聚合"""
    analytics = HarnessAnalytics(db)
    return ApiResponse(data=analytics.aggregate(user_id=user.id, days=days))

@router.post("/harness/entropy-check", response_model=ApiResponse[list[dict]])
def run_entropy_check(
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """手动触发 Entropy 检测（Admin only）"""
    analytics = HarnessAnalytics(db)
    detector = EntropyDetector(db, analytics)
    alerts = detector.detect()
    return ApiResponse(data=alerts)
```

## 验证步骤

```bash
# 1. 编译检查
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/services/harness_analytics.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/services/entropy_detector.py

# 2. 聚合逻辑测试（需要 runs 表有数据）
# 手动插入几条包含 harness_summary 的 runs 记录后：
docker compose -f docker-compose.dev.yml exec backend python -c "
from app.core.database import SessionLocal
from app.services.harness_analytics import HarnessAnalytics

with SessionLocal() as db:
    analytics = HarnessAnalytics(db)
    result = analytics.aggregate(days=30)
    print(f'Runs analyzed: {result[\"runs_analyzed\"]}')
    print(f'Averages: {result[\"averages\"]}')
    print('HarnessAnalytics: PASS')
"
```

## 完成后

1. 更新 PROGRESS.md
2. 更新 DECISIONS.md：记录 ADR-032（Entropy Detection 半自动模式——5 信号 + 7 天窗口对比）
3. 在 requirements.txt 中确认 `psutil` 已添加
4. 加载 Simplify skill 审查
5. 加载 PJR skill 验证
6. `git add -A && git commit -m "feat: Harness analytics + Entropy Detection (5 signals)"`
```

---

## Task 12.3: 运维配置与健康检查增强

### Part A — 设计与解释

#### 问题陈述

增强 `/health` 端点，从简单的 `{"status": "ok"}` 升级为包含资源监控数据的完整健康报告。同时完善 Docker Compose 的运维配置（日志、重启策略、资源限制）。

#### 验收标准

- `/health` 返回 Backend/DB/Redis 连接状态 + 内存用量 + 子进程数量
- `/health` 状态码：全部健康 200，部分警告 200（body 中 status=warning），严重问题 503
- Docker Compose 配置 restart 策略和日志限制
- 生产 nginx.conf 包含 SSE 透传配置

> **定时调度**：ResourceMonitor 通过 `asyncio` 后台任务定时运行（间隔通过 `RESOURCE_MONITOR_INTERVAL` 环境变量配置，默认 60 秒）。在 FastAPI `lifespan` 中启动和停止。

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在增强 Prism v2 的运维基础设施。

请先加载以下 Skill（如果找不到任何一个，立即停止并告知我）：
- using-superpowers

## 要修改的文件

```
backend/app/api/v1/health.py       # 增强健康检查
docker-compose.yml                  # 生产配置增强
nginx/nginx.conf                    # SSE 透传 + 安全头
```

## 实现规范

### 1. 健康检查增强

```python
@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    """
    增强健康检查。
    
    检查项：
    - DB 连接（SELECT 1）
    - Redis 连接（PING）
    - 内存用量（ResourceMonitor）
    - Agent 子进程状态
    
    返回:
    {
        "status": "ok" | "warning" | "critical",
        "checks": {
            "database": "ok",
            "redis": "ok",
            "memory": {"status": "ok", "backend_mb": 200, "system_percent": 45},
            "agents": {"running": 1, "max": 2},
        },
        "version": "2.0.0",
        "uptime_seconds": 3600,
    }
    """
    ...
```

### 2. docker-compose.yml 增强

```yaml
services:
  backend:
    restart: unless-stopped
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
    deploy:
      resources:
        limits:
          memory: 800M          # Backend 进程内存限制

  postgres:
    restart: unless-stopped
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

  redis:
    restart: unless-stopped
    command: redis-server --maxmemory 64mb --maxmemory-policy allkeys-lru
```

### 3. nginx.conf

```nginx
# SSE 透传配置
location /api/v1/sessions/ {
    proxy_pass http://backend:8000;
    proxy_set_header Connection "";
    proxy_buffering off;
    proxy_cache off;
    proxy_set_header X-Accel-Buffering no;
    proxy_read_timeout 3600s;     # SSE 长连接超时
}
```

## 验证步骤

```bash
# 增强健康检查
curl -s http://localhost:8000/health | python -m json.tool
# 期望：包含 database/redis/memory/agents 状态
```

## 完成后

1. 更新 PROGRESS.md
2. 加载 Simplify skill 审查
3. 加载 PJR skill 验证
4. `git add -A && git commit -m "feat: enhanced health check + Docker production config + nginx SSE"`
```

---

> **文档维护说明**：本文档的 3 个 Task 完成后，Prism v2 将拥有完整的可观测性和运维能力：TokenEstimator 策略模式（可替换精确计算）+ 资源监控（2C2G 约束下的内存/CPU 告警）+ 路由决策准确率追踪 + Harness Summary 聚合分析 + Entropy Detection（5 信号半自动检测 + 告警）+ 增强健康检查 + Docker 生产配置。  
> **最后更新**: 2026-04-02 | **全部文档完成**
