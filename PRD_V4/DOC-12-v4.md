# Prism 棱镜 v2 — Observability & Entropy (DOC-12)

> **文档编号**: DOC-12
> **版本**: 4.0(Review 修订版)
> **日期**: 2026-04-18
> **性质**: 实现文档 — 可观测性体系、熵管理、运维监控
> **前置依赖**: DOC-03 v4(Harness Runtime), DOC-07 v4(harness_summary schema), DOC-01 v4(服务拓扑 + 部署配置)
> **Phase**: 4(运维封装)
> **Task 数**: **7(v4 扩充:3 → 7,新增 4 个 Task)**
> **v4 变更摘要**: 基于 5 轮 review 修订,**28 处精确修补**(详见文末 §附录 A)。**本份文档是最大规模扩充(27KB → ~80KB)**。核心修订:TokenEstimator 直接上精确 tokenizer(CalibratingCharCountEstimator + AnthropicTokenCounter + TiktokenEstimator)、ResourceMonitor 按百分比阈值(70%/85%)而非绝对值、**Entropy 信号从 5 扩到 8**(加 Provider 健康度 / Cache 命中率 / permission_ask 超时率)、**阈值自动校准(ThresholdCalibrator 每周扫 30 天 harness_summary p90)**、**/health 拆分 live/ready/detailed**、Docker Compose 全部资源限制、**新增 Task 12.4 Prometheus Metrics(60+ 指标)**、**新增 Task 12.5 OTel Tracing**、**新增 Task 12.6 结构化日志**、**新增 Task 12.7 前端错误上报**、**新增 Task 12.8 告警通道 AlertDispatcher**。ADR 编号从 ADR-110 接续至 ADR-120。
> **审计关注点**:
> - **内存用量监控(2C2G 约束)**:v4 按百分比阈值(70% warn / 85% critical)而非绝对值,兼容升级到 4C4G 或降级到 1C1G
> - **路由决策准确率追踪**:DOC-04 v4 Task 4.4 的 TaskRouter 使用关键词匹配,追踪准确率(用户手动覆盖 agent_type 比例 = 路由不准确信号)
> - **TokenEstimator**:v4 直接上精确 tokenizer(CharCount 保留但作 fallback 兜底),不再留"等以后"
> - **harness_summary 消费与展示**:DOC-07 v4 定义 schema,本文档定义聚合/分析/展示

---

## 目录

1. [Task 12.1: TokenEstimator 接口与资源监控(v4:精确 tokenizer)](#task-121-tokenestimator-接口与资源监控)
2. [Task 12.2: Harness 数据聚合与 Entropy Detection(v4:8 信号 + 阈值自动校准)](#task-122-harness-数据聚合与-entropy-detection)
3. [Task 12.3: 运维配置与健康检查增强(v4:/health 拆 3 子端点 + 资源限制)](#task-123-运维配置与健康检查增强)
4. [**Task 12.4: Prometheus Metrics(v4 新增)**](#task-124-prometheus-metrics)
5. [**Task 12.5: OTel Tracing(v4 新增)**](#task-125-otel-tracing)
6. [**Task 12.6: 结构化日志(v4 新增)**](#task-126-结构化日志)
7. [**Task 12.7: 前端错误上报(v4 新增)**](#task-127-前端错误上报)
8. [**Task 12.8: 告警通道 AlertDispatcher(v4 新增)**](#task-128-告警通道-alertdispatcher)

---

## Task 12.1: TokenEstimator 接口与资源监控

### Part A — 设计与解释

#### 问题陈述

DOC-02 Task 2.4 的 `ContextBudgetManager.estimate_tokens()` 使用粗略的字符计数（1 token ≈ 4 英文字符 / 1.5 中文字符），误差在 20-30%。这对 Compaction 的阈值判断影响较大——可能过早触发（浪费上下文空间）或过晚触发（API 报错）。

需要一个可替换的 `TokenEstimator` 接口，Phase 1 使用字符计数（零依赖，ms 级），Phase 2 可切换到 tiktoken/tokenizers（精确但需要额外依赖）。

同时，Prism 运行在 2C2G 的资源约束下，需要监控内存用量并在接近阈值时告警。

#### 设计决策(ADR)

- **ADR-110(精确 tokenizer 直接上)**:TokenEstimator 策略模式,v4 **直接上精确 tokenizer**:
  - 接口:`estimate(text: str, model: str | None) -> int`
  - 实现 1:`AnthropicTokenCounter` — 用 Anthropic SDK `count_tokens`(精确,Claude 模型首选)
  - 实现 2:`TiktokenEstimator` — tiktoken cl100k_base(OpenAI / DeepSeek 等用)
  - 实现 3:`CalibratingCharCountEstimator` — 字符计数但根据实际 usage feedback 动态校准系数(fallback,当 1/2 不可用时)
  - 通过 Provider capabilities 动态选择(DOC-02 v4 ADR-009)

  来源:Batch 5 §A12-1。

- **ADR-111(ResourceMonitor 按百分比阈值)**:资源监控从"绝对值 1.5GB"改为"百分比阈值"(70% warn / 85% critical),兼容升级到 4C4G 或降级到 1C1G。额外监控:CPU % / 子进程数 / 队列深度。来源:Batch 5 §A12-2。

#### 验收标准(v4 扩展)

- TokenEstimator 接口定义清晰,三个实现可互换
- **v4:AnthropicTokenCounter 对 Claude 模型精确计数,TiktokenEstimator 对 OpenAI/通用模型使用**
- **v4:CalibratingCharCountEstimator 根据 usage feedback 动态校准系数**(observer 模式,每次 stream 后用 actual vs estimate 比值更新)
- ContextBudgetManager 重构为依赖注入 TokenEstimator
- 内存监控能获取 Backend 进程和子进程的 RSS
- **v4:内存超过 70% warn / 85% critical 通过 AlertDispatcher 告警**(Task 12.8)
- **v4:ResourceMonitor 扩展监控 CPU% / 子进程数 / 队列深度**
- 路由决策准确率可查询(从 runs 表统计 agent_type override 比例)

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

## Task 12.2: Harness 数据聚合与 Entropy Detection(v4:8 信号 + 阈值自动校准)

### Part A — 设计与解释

#### 问题陈述

DOC-07 v4 定义了 `runs.harness_summary` JSONB 的完整 schema。本 Task 实现对这些数据的聚合分析和 Entropy Detection(熵漂移检测)。

Entropy 是指 Agent 输出质量随时间退化的现象——格式漂移、指令遵循率下降、工具调用模式异常。OpenAI Codex 团队每周花 20% 时间清理 AI slop,Prism 将这个过程系统化为检测 + 告警 + 人工触发清理。

**v4 核心修订**:
1. Entropy 信号从 **5 个扩到 8 个**(加 Provider 健康度下降 / Cache 命中率下降 / permission_ask 超时率上升)
2. `HarnessAnalytics.aggregate()` 返回结构加 **cache_stats**(hit_tokens / miss_tokens / creation_tokens / hit_ratio / creation_cost_ratio / by_provider)
3. **ThresholdCalibrator 阈值自动校准**:每周扫 30 天 harness_summary p90 校准阈值,平滑过渡 `0.7*current + 0.3*p90`

#### Entropy 检测信号(v4:8 个)

| 信号 | 来源 | 阈值(可自动校准) | 含义 |
|------|------|------|------|
| 护栏触发率上升 | harness_summary.guardrail_triggers / turn_count | > 0.3 | Agent 越来越频繁触碰护栏 |
| 工具错误率上升 | harness_summary.total_tool_errors / total_tool_calls | > 0.2 | 工具调用质量下降 |
| Compaction 频率上升 | compaction_events / turn_count | > 0.2 | 上下文管理压力增大 |
| 循环检测命中 | loop_detections > 0 | > 0 | Agent 陷入重复模式 |
| 平均 turn_count 上升 | 近 7 天 vs 前 7 天的平均 turn_count | 增长 > 50% | 任务完成效率下降 |
| **v4: Provider 健康度下降** | prism_provider_failover_total 日增速 | 增速 > 30% | Provider 故障变频 |
| **v4: Cache 命中率下降** | cache_hit_tokens / total_input_tokens 周比 | 下降 > 20 pp | Prompt 缓存效率退化 |
| **v4: permission_ask 超时率上升** | permission_ask_timeout / permission_ask_total | > 0.15 | 用户放任或 UI 问题 |

#### 设计决策(ADR)

- **ADR-112(Entropy 信号扩展)**:从 5 扩到 8,覆盖 Provider 健康、Cache 效率、permission 交互完整性三个新维度。来源:Batch 5 §A12-3/§A12-4。

- **ADR-113(阈值自动校准)**:ThresholdCalibrator 每周扫 30 天 harness_summary,对每个信号计算 p90,用 `new = 0.7 * current + 0.3 * p90` 平滑过渡(避免阈值剧烈跳动导致误告警)。人工审核通过后生效。来源:Batch 5 §A12-5。

#### Entropy Detection 模式(Phase 1:半自动)

1. **检测**:定时分析 harness_summary 数据,计算 8 个信号
2. **告警**:超过阈值时写入 entropy_alerts 表 + audit_logs(action: `harness.entropy_alert`)+ 通过 AlertDispatcher 分发(Task 12.8)
3. **人工触发清理**:Admin 查看告警后决定是否调整 Prompt / 护栏规则 / 工具配置

不做全自动规则生成(P7 可撕裂原则——避免"修复 AI 输出的 AI"引入新的不确定性)。

> **窗口修复 (P0)**:`HarnessAnalytics.aggregate()` 增加 `offset_days: int = 0` 参数。EntropyDetector 使用非重叠窗口:
> ```python
> current = analytics.aggregate(days=7, offset_days=0)   # 最近 7 天
> previous = analytics.aggregate(days=7, offset_days=7)   # 7~14 天前
> ```
> 两个窗口不重叠,delta 计算才有意义。

#### 验收标准(v4 扩展)

- HarnessSummaryAggregator 能聚合最近 N 天的 harness_summary 数据
- **v4:聚合结果含 `cache_stats`**(hit_tokens / miss_tokens / creation_tokens / hit_ratio / creation_cost_ratio / by_provider)
- **v4:Entropy Detection 能计算 8 个信号指标**
- 超过阈值时生成告警记录(entropy_alerts 表)
- 提供查询接口供 Admin 面板展示(DOC-11 v4 Task 11.6)
- **v4:ThresholdCalibrator 可运行(手动触发或每周 Cron)**,输出建议阈值供 Admin 审核
- 定时任务(或手动触发)执行检测

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

## Task 12.3: 运维配置与健康检查增强(v4:/health 拆 3 子端点 + 完整资源限制)

### Part A — 设计与解释

#### 问题陈述

增强 `/health` 端点,从简单的 `{"status": "ok"}` 升级为 **3 个子端点**。同时完善 Docker Compose 的运维配置(日志、重启策略、**全部服务资源限制**)。

#### 设计决策(ADR)

- **ADR-114(/health 拆分为 3 个子端点)**:
  - **`/health/live`** — liveness probe,始终返回 200 只要进程活着,用于 K8s/Docker 重启判断。**不** 检查依赖,最快响应
  - **`/health/ready`** — readiness probe,检查 DB + Redis + 关键依赖;任何 critical 依赖不可用返回 503,用于 LB 摘除
  - **`/health/detailed`** — admin only,完整健康报告,包含资源监控 / 子进程 / 各 Provider 熔断状态

  来源:Batch 5 §A12-6。

- **ADR-115(Docker Compose 全部资源限制)**:backend / postgres / redis / nginx 每个服务都必须有 `deploy.resources.limits + reservations` + `healthcheck`,用 ADR-114 的 `/health/live` 作为 healthcheck。来源:Batch 5 §A12-7。

#### 验收标准(v4 扩展)

- **v4:`/health/live` 返回 200 + `{"status":"ok"}`,不查任何依赖**
- **v4:`/health/ready` 检查 DB + Redis,任何不可用返回 503**
- **v4:`/health/detailed`(admin only)返回完整报告**:Backend/DB/Redis 连接状态 + 内存用量 + 子进程数量 + Provider 熔断状态
- **v4:Docker Compose backend/postgres/redis/nginx 4 个服务每个都有 limits + reservations + healthcheck**
- 生产 nginx.conf 包含 SSE 透传配置(`X-Accel-Buffering: no` + `proxy_read_timeout 3600s`)

> **定时调度**:ResourceMonitor 通过 `asyncio` 后台任务定时运行(间隔通过 `RESOURCE_MONITOR_INTERVAL` 环境变量配置,默认 60 秒)。在 FastAPI `lifespan` 中启动和停止。

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

### 1. 健康检查拆分(v4 ADR-114)

```python
# app/api/v1/health.py(v4)
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def liveness():
    """v4:liveness probe — 只要进程活着就 200,不查任何依赖"""
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness(db = Depends(get_db), redis_client = Depends(get_redis)):
    """v4:readiness probe — 检查 DB + Redis,critical 依赖不可用返回 503"""
    checks = {}
    healthy = True
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"
        healthy = False

    try:
        await redis_client.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"
        healthy = False

    if not healthy:
        raise HTTPException(503, detail={"status": "unhealthy", "checks": checks})
    return {"status": "ok", "checks": checks}


@router.get("/health/detailed")
async def detailed_health(
    admin = Depends(require_admin),
    db = Depends(get_db),
    redis_client = Depends(get_redis),
):
    """v4:admin-only 完整健康报告"""
    # 同上 readiness,再加 memory/agents/providers 信息
    return {
        "status": "ok",
        "checks": {
            "database": "ok",
            "redis": "ok",
            "memory": {
                "status": "ok",
                "backend_mb": 200,
                "system_percent": 45,
                "thresholds": {"warn": 70, "critical": 85},
            },
            "agents": {"running": 1, "max": 2},
            "providers": {"healthy": 3, "broken": 0},
        },
        "version": "2.0.0",
        "uptime_seconds": 3600,
    }
```

### 2. docker-compose.yml 完整资源限制(v4 ADR-115)

```yaml
services:
  backend:
    image: prism-backend:2.0
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:8000/api/v1/health/live"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s
    logging:
      driver: json-file
      options: { max-size: "10m", max-file: "3" }
    deploy:
      resources:
        limits: { cpus: "1.5", memory: 1200M }
        reservations: { cpus: "0.5", memory: 400M }

  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER:-prism}"]
      interval: 30s
      timeout: 5s
      retries: 3
    logging:
      driver: json-file
      options: { max-size: "10m", max-file: "3" }
    deploy:
      resources:
        limits: { cpus: "0.5", memory: 500M }
        reservations: { cpus: "0.2", memory: 200M }

  redis:
    image: redis:7-alpine
    command: ["redis-server", "--appendonly", "yes", "--maxmemory", "128mb", "--maxmemory-policy", "allkeys-lru"]
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 30s
      timeout: 3s
      retries: 3
    logging:
      driver: json-file
      options: { max-size: "10m", max-file: "3" }
    deploy:
      resources:
        limits: { cpus: "0.3", memory: 200M }
        reservations: { cpus: "0.1", memory: 80M }

  nginx:
    image: nginx:1.27-alpine
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost/healthz"]
      interval: 30s
      timeout: 3s
      retries: 3
    deploy:
      resources:
        limits: { cpus: "0.3", memory: 150M }
        reservations: { cpus: "0.1", memory: 50M }
```

### 3. nginx.conf(v4:SSE 透传 + 资源限制兼容)

```nginx
server {
    listen 80;

    # 静态健康检查端点(nginx 自身)
    location = /healthz {
        access_log off;
        return 200 "ok\n";
    }

    # SSE 透传配置(关键 v4 要求)
    location ~ ^/api/v1/sessions/[^/]+/stream {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_set_header X-Accel-Buffering no;
        proxy_read_timeout 3600s;     # SSE 长连接超时
        chunked_transfer_encoding off;
    }

    location / {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
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

---

## Task 12.4: Prometheus Metrics(v4 新增)

### Part A — 设计与解释

#### 问题陈述

Prism v4 需要完整的 Prometheus 指标采集体系,覆盖 Run / TAOR / 工具 / Harness / Model / Permission / Session / Provider / IM / 子进程 10 大维度,共 60+ 指标。所有指标通过 `/metrics` 端点暴露(Prometheus 默认 scrape),Grafana 4 套 dashboard 消费。

#### 设计决策(ADR)

- **ADR-116(Prometheus metrics 10 维度覆盖 + Grafana 4 dashboard)**:Backend + Executor 都注册指标到共享 registry,通过 `/metrics` 端点暴露。Grafana 4 套 dashboard JSON 文件随 docker-compose.monitoring.yml 开箱即用:`prism-overview.json / prism-harness.json / prism-models.json / prism-agents.json`。

#### Metrics 目录(10 大维度)

**Run 级**
- `prism_runs_total{status,agent_type}` counter
- `prism_run_duration_seconds{agent_type}` histogram
- `prism_run_turn_count{agent_type}` histogram
- `prism_run_tokens_total{kind:input|output|cache_hit|cache_creation}` counter
- `prism_run_cost_usd_total{provider}` counter

**TAOR 级**
- `prism_turn_duration_seconds{agent_type}` histogram
- `prism_turn_stop_reason_total{reason}` counter

**工具级**
- `prism_tool_invocations_total{tool_name}` counter
- `prism_tool_duration_seconds{tool_name}` histogram
- `prism_tool_errors_total{tool_name,error_type}` counter
- `prism_tool_truncation_total{tool_name}` counter

**Harness 级**
- `prism_harness_guardrail_triggers_total{rule_id}` counter
- `prism_harness_permission_ask_total{decision:allow|deny|timeout}` counter
- `prism_harness_hook_invocations_total{event_type,handler_type}` counter
- `prism_harness_compaction_total{tier:1|2|4}` counter
- `prism_harness_feedback_total{event_type,severity}` counter
- `prism_harness_memory_extracted_total` counter
- `prism_permission_answered_total{decision}` counter

**Model 级**
- `prism_model_request_duration_seconds{provider,model}` histogram
- `prism_model_tokens_total{provider,model,kind}` counter
- `prism_model_cache_hit_ratio{provider,model}` gauge
- `prism_model_errors_total{provider,model,error_type}` counter

**Permission 级**(同 Harness,按 tool 粒度)

**Session 级**
- `prism_sessions_active` gauge
- `prism_session_queue_length` gauge
- `prism_sse_tickets_issued_total` counter
- `prism_sse_connections_active{session_id}` gauge

**Provider 级**
- `prism_provider_healthy{provider_id}` gauge(0/1)
- `prism_provider_failover_total{from,to}` counter
- `prism_provider_circuit_breaks_total{provider_id,reason}` counter

**IM 级**
- `prism_im_messages_total{channel}` counter
- `prism_im_webhook_duplicates_total{channel}` counter
- `prism_im_bindings_active{channel}` gauge

**子进程级**
- `prism_agent_subprocess_running` gauge
- `prism_agent_heartbeat_stale_total` counter
- `prism_agent_subprocess_crashed_total{reason}` counter

**前端级**(Task 12.7 补)
- `prism_frontend_errors_total{severity,viewport}` counter
- `prism_web_vitals_histogram{metric,route}` histogram

#### Grafana Dashboard 4 套

位置:`monitoring/grafana/dashboards/*.json`
- `prism-overview.json` — Runs/s / Errors/s / P95 latency / 活跃 Session 数
- `prism-harness.json` — guardrail / permission / hook 事件时序 + compaction 分布
- `prism-models.json` — tokens / cost / cache / provider health
- `prism-agents.json` — 子进程 / fork / background / heartbeat 生命周期

provisioning:`monitoring/grafana/provisioning/` 配置 auto-load dashboards + datasource(Prometheus)。

#### 验收标准

- `/metrics` 端点返回 Prometheus 格式指标(text/plain)
- 10 个维度的 60+ 指标全部注册
- 业务关键路径(run / tool / hook / permission / compaction)均有 counter + histogram
- Grafana 4 套 dashboard JSON 文件随 docker-compose.monitoring.yml 开箱启动
- Prometheus 配置 scrape backend + executor 两个端点(executor 子进程用 push gateway 或 sidecar)

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 要创建的文件

```
backend/app/observability/
├── metrics.py                        # 统一 registry + 所有指标定义
└── prometheus_asgi.py                # ASGI /metrics 路由

executor/observability/
└── metrics.py                        # 子进程指标(text pushgateway 或 sidecar)

monitoring/
├── docker-compose.monitoring.yml     # Prometheus + Grafana 服务
├── prometheus/
│   └── prometheus.yml                # scrape 配置
└── grafana/
    ├── provisioning/
    │   ├── datasources/prometheus.yml
    │   └── dashboards/dashboards.yml
    └── dashboards/
        ├── prism-overview.json
        ├── prism-harness.json
        ├── prism-models.json
        └── prism-agents.json
```

## 实现示例:metrics.py

```python
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry

REGISTRY = CollectorRegistry()

prism_runs_total = Counter(
    "prism_runs_total", "Total runs created",
    ["status", "agent_type"], registry=REGISTRY,
)
prism_run_duration_seconds = Histogram(
    "prism_run_duration_seconds", "Run duration",
    ["agent_type"],
    buckets=(1, 5, 10, 30, 60, 180, 600, 1800),
    registry=REGISTRY,
)
# ... 其余 60+ 指标按 Part A 目录列表定义
```

### /metrics 端点

```python
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

@app.get("/metrics")
async def metrics(admin=Depends(require_admin)):
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
```

## 验证步骤

```bash
curl -s http://localhost:8000/metrics | head -40
# 期望看到 prism_runs_total / prism_tool_invocations_total 等

# 启动监控栈
docker compose -f monitoring/docker-compose.monitoring.yml up -d
# 访问 http://localhost:3001(Grafana) 查看 4 套 dashboard
```

## 完成后

1. 更新 DECISIONS.md:记录 ADR-116
2. `git add -A && git commit -m "feat(v4): prometheus metrics (60+ indicators) + 4 grafana dashboards"`
```

---

## Task 12.5: OTel Tracing(v4 新增)

### Part A — 设计与解释

#### 问题陈述

Prism v4 跨进程操作多(Backend → 子进程 → Adapter → Provider → 工具),需要分布式 tracing 定位性能瓶颈和错误路径。使用 OpenTelemetry(OTLP exporter,后端可选 Jaeger / Tempo / Honeycomb / 云厂商)。

#### 设计决策(ADR)

- **ADR-117(OTel TracerProvider + 跨进程传播)**:
  - Backend + Executor 各自初始化 TracerProvider,连接同一个 OTLP endpoint
  - 核心 span 树:`run → taor_turn → prompt_assembly → model_request → tool_use → middleware_chain`
  - 跨进程:Backend 启动 subprocess 时传 `--otel-trace-id=traceparent-value`(W3C TraceContext),子进程根据该值继续当前 trace
  - 关键 trace 标签(attributes):`run.id / session.id / user.id / agent.type / route.mode / tool.name / provider.name / model.id / harness.guardrail_triggered / harness.permission_decision`

#### 核心 span 树结构

```
run (root span, run_id)
├── taor_turn#1 (turn_count=1)
│   ├── prompt_assembly (tokens_estimated=...)
│   ├── model_request (provider=..., model=..., cache_hit_tokens=...)
│   ├── tool_use[0] (tool_name=Bash, duration_ms=...)
│   │   ├── hook.pre_tool_use
│   │   ├── permission.check
│   │   └── tool.execute
│   └── middleware_chain (post_turn)
├── taor_turn#2
...
└── compaction (tier=2, before=..., after=...)
```

### Part B — 实现规范

```
backend/app/observability/tracing.py
executor/observability/tracing.py
```

```python
# backend/app/observability/tracing.py
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter


def init_tracing(settings):
    resource = Resource.create({
        "service.name": "prism-backend",
        "service.version": "2.0.0",
    })
    provider = TracerProvider(resource=resource)
    if settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(
            endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT,
        )))
    else:
        # dev 环境:stdout exporter
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    return trace.get_tracer("prism-backend")


tracer = init_tracing(settings)
```

调用处:

```python
with tracer.start_as_current_span("run", attributes={
    "run.id": run_id, "session.id": session_id, "user.id": user_id,
    "agent.type": agent_type,
}) as span:
    ...
```

跨进程:Backend `process_manager._build_command()` 从当前 span 的 context 取 traceparent 头(W3C),作为 `--otel-trace-id` 参数传给子进程;子进程 `executor/__main__.py` 收到后调 `trace.set_current_context(TraceContextTextMapPropagator().extract({"traceparent": args.otel_trace_id}))` 继续当前 trace。

#### 验收标准

- OTel TracerProvider 初始化 + OTLP/stdout exporter
- 核心 span 树完整覆盖(run / taor_turn / prompt_assembly / model_request / tool_use / middleware_chain / compaction)
- 跨进程 trace 通过 W3C TraceContext 头传播,Backend span 能在子进程内的 span 中看到同一 trace_id
- 关键 attributes 按 ADR-117 清单标注
- OTLP endpoint 可通过环境变量配置;未配置时降级为 stdout(dev 友好)

## 完成后

1. 更新 DECISIONS.md:记录 ADR-117
2. `git add -A && git commit -m "feat(v4): opentelemetry tracing with cross-process propagation"`

---

## Task 12.6: 结构化日志(v4 新增)

### Part A — 设计与解释

#### 问题陈述

Prism v4 所有日志必须结构化(JSON)输出,便于 Loki / CloudWatch / ELK 检索。使用 `structlog`,通过 `contextvars` 自动绑定 run_id / session_id / user_id。

#### 设计决策(ADR)

- **ADR-118(structlog + contextvars 自动绑定 + JSON 输出)**:
  - 全局 logger 用 `structlog.get_logger()`
  - 中间件在请求进入时 bind `request_id / user_id` 到 contextvars
  - QueryEngine 在 run 开始时 bind `run_id / session_id / agent_type`
  - 事件名约定:`{domain}.{action}`(例:`run.started` / `harness.guardrail.triggered` / `tool.invoked` / `callback.received`)
  - 日志级别:
    - DEBUG:流事件(text_delta 不记,但 message_complete 记)
    - INFO:生命周期(run.started/completed, tool.invoked)
    - WARNING:降级(callback.server_error,retrying)
    - ERROR:失败(run.failed, tool.exception)
    - CRITICAL:崩溃(subprocess.crashed, unhandled)

### Part B — 实现规范

```python
# app/observability/logging.py
import structlog, logging
from structlog.contextvars import merge_contextvars

def init_logging(level: str = "INFO"):
    structlog.configure(
        processors=[
            merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level)),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
```

调用:
```python
logger.info("run.started", run_id=run_id, agent_type=agent_type, prompt_preview=prompt[:50])
logger.error("tool.exception", tool_name=name, error=str(e), exc_info=True)
```

#### 验收标准

- 所有日志 JSON 格式输出(stdout)
- contextvars 自动附加:request_id / user_id / run_id / session_id / agent_type
- 事件名遵循 `{domain}.{action}` 规范
- 日志级别按 ADR-118 分档使用
- 关键事件:run.started/completed/failed/crashed / tool.invoked/exception / harness.guardrail.triggered / harness.permission.asked / harness.compaction.tier{N} / callback.received/failed/dlq / heartbeat.stale

## 完成后

1. 更新 DECISIONS.md:ADR-118
2. `git add -A && git commit -m "feat(v4): structured logging with structlog + contextvars"`

---

## Task 12.7: 前端错误上报(v4 新增)

### Part A — 设计与解释

#### 问题陈述

DOC-10 v4 ADR-095 规定前端 ErrorBoundary / window.onerror / unhandledrejection 通过 `POST /api/v1/frontend-errors` 上报到 Backend。Backend 需要实现接收端点 + 写 audit_logs + Prometheus metric。

#### 设计决策(ADR)

- **ADR-119(/frontend-errors 端点 + schema)**:
  - Body schema:`FrontendErrorPayload { message / stack / name / url / user_agent / viewport / user_id / context / severity / timestamp }`
  - 无需认证(允许未登录错误,如登录页本身报错),但做 IP 级别 rate limit 避免滥用
  - 写 `audit_logs`(action=`frontend.error`, severity=payload.severity)
  - `prism_frontend_errors_total{severity,viewport}` counter 自增

### Part B — 实现规范

```python
# app/schemas/frontend.py
class FrontendErrorPayload(BaseModel):
    message: str
    stack: str | None = None
    name: str | None = None
    url: str | None = None
    user_agent: str | None = None
    viewport: str | None = None
    user_id: str | None = None
    session_id: str | None = None
    context: dict = {}
    severity: Literal["info", "warning", "error", "critical"] = "error"
    timestamp: str | None = None


# app/api/v1/frontend.py
@router.post("/frontend-errors", status_code=204)
async def report_frontend_error(
    payload: FrontendErrorPayload,
    request: Request,
    db = Depends(get_db),
):
    # 简单 IP rate limit(Redis SETNX counter)
    # ...
    viewport_bucket = _classify_viewport(payload.viewport)
    db.add(AuditLog(
        user_id=payload.user_id,
        action="frontend.error",
        severity=payload.severity,
        details={
            "message": payload.message[:500],
            "stack": (payload.stack or "")[:2000],
            "url": payload.url,
            "viewport": payload.viewport,
            "context": payload.context,
        },
    ))
    db.commit()
    prism_frontend_errors_total.labels(
        severity=payload.severity,
        viewport=viewport_bucket,
    ).inc()


def _classify_viewport(v: str | None) -> str:
    if not v:
        return "unknown"
    try:
        w = int(v.split("x")[0])
        if w < 640: return "mobile"
        if w < 1024: return "tablet"
        return "desktop"
    except Exception:
        return "unknown"
```

#### 验收标准

- `POST /api/v1/frontend-errors` 接受 FrontendErrorPayload,返回 204
- 写入 audit_logs 表,action=frontend.error
- Prometheus counter `prism_frontend_errors_total{severity,viewport}` 自增
- IP rate limit 防滥用(默认每 IP 每分钟 ≤60 条)
- 无认证要求,但请求来源必须通过 CSRF 同源校验(或在 nginx 层限制 Referer)

## 完成后

1. 更新 DECISIONS.md:ADR-119
2. `git add -A && git commit -m "feat(v4): frontend error reporter endpoint + audit + prom metric"`

---

## Task 12.8: 告警通道 AlertDispatcher(v4 新增)

### Part A — 设计与解释

#### 问题陈述

Prism 需要统一的告警分发(audit / SSE / IM / email)按 severity 分档。DOC-07 v4 Task 7.4 定义了 AlertDispatcher 骨架,本 Task 补完具体分发策略 + IM 告警(复用 DOC-08 v4 IM Gateway) + email(可选 Phase 2)。

#### 设计决策(ADR)

- **ADR-120(AlertDispatcher severity 分档)**:
  - `info`:仅 structlog(不写 audit)
  - `warning`:audit_logs
  - `error`:audit_logs + 用户 SSE alert 事件(若 user_id 可推)
  - `critical`:上述 + IM 群告警(admin 配置的 ALERT_IM_CHANNEL)+ email(可选)

  admin 在 settings 可配置"critical 告警发到 X 群"。IM 告警消息体含 event_type + detail preview + 告警详情页链接。

### Part B — 实现规范

见 DOC-07 v4 Task 7.4 `alert_dispatcher.py` 骨架。本 Task 补齐:

1. IM 告警格式化函数 `_format_im_message(event_type, detail)`(Markdown,含链接)
2. email 支持(Phase 1 可用 SMTP / Phase 2 接 SES/SendGrid)
3. admin 配置端点 `PATCH /admin/alerts/config`(写 `alert_configs` 表 或 settings)
4. Entropy Detector(Task 12.2)调用 AlertDispatcher.dispatch("error"/"critical", "harness.entropy_alert", detail)
5. HeartbeatMonitor(DOC-07 v4 Task 7.3)调用 AlertDispatcher.dispatch("critical", "run.crashed", detail)
6. ResourceMonitor(Task 12.1)调用 AlertDispatcher.dispatch("warning" when 70%+/"critical" when 85%+, "resource.memory", detail)

#### 验收标准

- AlertDispatcher 按 severity 分档分发
- IM 告警走 DOC-08 v4 IM Gateway 发送(不新造 IM 适配)
- email 可选(Phase 1 SMTP,未配置时降级只写 audit)
- admin 配置 ALERT_IM_CHANNEL 生效
- Entropy / Heartbeat / Resource 三类触发点全部接入 AlertDispatcher

## 完成后

1. 更新 DECISIONS.md:ADR-120
2. `git add -A && git commit -m "feat(v4): alert dispatcher with severity routing (audit/sse/im/email)"`

---

## 附录 A: v4 修订清单

本次修订共 28 处精确修补,对应 Batch 1-5 review + Master:

| # | 位置 | 修订内容 | 来源 |
|---|---|---|---|
| 1 | Header | 版本 3.1 → 4.0,日期 2026-04-18,Task 数 3 → 7(后修为 8 含新增 4 项),v4 摘要段,目录重写 | 全局 + Batch 5 §B5-I |
| 2 | Task 12.1 Part A | ADR-110(精确 tokenizer 直接上)/ADR-111(ResourceMonitor 按百分比) | Batch 5 §A12-1/§A12-2 |
| 3 | Task 12.1 TokenEstimator | 重构:CalibratingCharCountEstimator(有 usage feedback 时动态校准系数) + AnthropicTokenCounter + TiktokenEstimator | Batch 5 §A12-1 |
| 4 | Task 12.1 ResourceMonitor | 按百分比阈值(70/85) + 绝对值 fallback + CPU + 子进程数 + 队列深度 | Batch 5 §A12-2 |
| 5 | Task 12.2 Part A | ADR-112(Entropy 信号从 5 扩到 8)/ADR-113(阈值自动校准) | Batch 5 §A12-3/§A12-4/§A12-5 |
| 6 | Task 12.2 HarnessAnalytics.aggregate() | 返回结构加 cache_stats(hit_tokens / miss_tokens / creation_tokens / hit_ratio / creation_cost_ratio / by_provider) | Batch 5 §A12-3 |
| 7 | Task 12.2 EntropyDetector 8 信号 | 原 5 个 + Provider 健康度下降 + Cache 命中率下降 + permission_ask 超时率上升 | Batch 5 §A12-4 |
| 8 | Task 12.2 ThresholdCalibrator(新) | 每周扫 30 天 harness_summary,p90 校准阈值,平滑过渡 0.7*current + 0.3*p90 | Batch 5 §A12-5 |
| 9 | Task 12.3 Part A | ADR-114(/health 拆 liveness/readiness/detailed) / ADR-115(Docker Compose 全部资源限制) | Batch 5 §A12-6/§A12-7 |
| 10 | Task 12.3 /health 拆分 | `/health/live`(200 进程活) / `/health/ready`(503 若任何依赖 critical) / `/health/detailed`(admin only) | Batch 5 §A12-6 |
| 11 | Task 12.3 Docker Compose | backend/postgres/redis/nginx 每个都有 limits + reservations + healthcheck | Batch 5 §A12-7 |
| 12 | Task 12.3 nginx.conf SSE 透传 | `X-Accel-Buffering: no` + `proxy_read_timeout 3600s` + chunked_transfer_encoding off | — |
| 13 | **新 Task 12.4(Prometheus Metrics)** | 60+ 指标定义 + `/metrics` 端点 + 10 维度覆盖;ADR-116 | Batch 5 §B5-I |
| 14 | Task 12.4 metrics 覆盖面 | Run / TAOR / 工具 / Harness / Model / Permission / Session / Provider / IM / 子进程 / 前端 | 同上 |
| 15 | Task 12.4 Grafana Dashboard | 4 套 dashboard JSON 文件 + docker-compose.monitoring.yml 开箱 | Batch 5 §B5-V |
| 16 | Task 12.4 provisioning | Grafana auto-load dashboards + datasource | Batch 5 §B5-V |
| 17 | **新 Task 12.5(OTel Tracing)** | ADR-117:TracerProvider + OTLP/Stdout + 核心 span 树 + W3C 跨进程 | Batch 5 §B5-I |
| 18 | Task 12.5 跨进程 trace | Backend 子进程启动时传 OTEL_TRACE_ID/traceparent | 同上 |
| 19 | Task 12.5 关键 trace 标签 | run.id/session.id/user.id/agent.type/route.mode/tool.name/provider.name/model.id/harness.guardrail_triggered | 同上 |
| 20 | **新 Task 12.6(结构化日志)** | ADR-118:structlog + contextvars 自动绑定 + JSON 输出 + 日志级别规范 + 事件名约定 | Batch 5 §B5-I |
| 21 | **新 Task 12.7(前端错误上报)** | ADR-119:`POST /frontend-errors` + FrontendErrorPayload schema + 写 audit_logs + IP rate limit | Batch 5 §B5-I, Batch 4 §B4-I |
| 22 | Task 12.7 Prometheus metric | `prism_frontend_errors_total{severity,viewport}` + viewport 三分档(mobile/tablet/desktop) | 同上 |
| 23 | **新 Task 12.8(告警通道 AlertDispatcher)** | ADR-120:audit/SSE/IM/email 按 severity 分档 + admin 配置 ALERT_IM_CHANNEL | Batch 5 §B5-IV |
| 24 | Task 12.8 IM 告警 | 复用 DOC-08 v4 IM Gateway,admin settings 配置 critical 告警群 | 同上 |
| 25 | 所有 Task Part B | v4 Observability 自引用,跨 Task 调用关系(Entropy → AlertDispatcher,Heartbeat → AlertDispatcher,Resource → AlertDispatcher) | 全局 |
| 26 | ADR 编号 ADR-110~120 | 全局 | 全局 |
| 27 | 目录 | 3 项 → 8 项 | Batch 5 §B5-I |
| 28 | 附录 A + 文末 | 修订清单 + "全部文档完成" | SOP |

---

> **文档维护说明(v4)**:本文档的 8 个 Task 完成后,Prism v2 将拥有完整的可观测性和运维能力:**TokenEstimator 精确 tokenizer(CalibratingCharCount + AnthropicTokenCounter + TiktokenEstimator)** + **ResourceMonitor 百分比阈值** + 路由决策准确率追踪 + Harness Summary 聚合分析(**含 cache_stats**)+ **Entropy Detection 8 信号**(+ Provider 健康 / Cache 命中 / permission_ask 超时)+ **ThresholdCalibrator 阈值自动校准** + **`/health` 3 子端点**(live/ready/detailed)+ **Docker Compose 全部资源限制(backend/postgres/redis/nginx)** + **Prometheus 60+ 指标 10 维度 + 4 套 Grafana Dashboard 开箱** + **OTel Tracing 跨进程**(run→taor_turn→prompt_assembly→model_request→tool_use→middleware_chain)+ **结构化日志 structlog + contextvars + JSON** + **前端错误上报端点 + `prism_frontend_errors_total`** + **AlertDispatcher 按 severity 分档分发(audit/SSE/IM/email)**。这是 Prism v2 全部 13 份 PRD 文档(DOC-00 ~ DOC-12)的最后一份,至此 Prism v2 的 PRD 体系完整交付。
> **最后更新**: 2026-04-18 (v4 review 修订版) | **PRD 体系完成**:DOC-00~12 全部 v4 化,ADR 累计 120 个,共同构成 Prism v2 Sonnet 4.6 可零猜测开写的完整蓝图。下一步交付:**DOC-CC-ONBOARDING.md**(Claude Code 先导文档)。
> **最后更新**: 2026-04-02 | **全部文档完成**
