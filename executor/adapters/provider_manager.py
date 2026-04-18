"""
Prism v2 — Provider Manager (DOC-02 Task 2.3)

ProviderManager 运行在 Executor(子进程)侧。

进程边界(CLAUDE.md 六原则 #6):
  - 绝不 import backend.app.* 任何模块
  - 构造时接受已解密的 API Key 列表(Backend 侧解密,通过参数传入)
  - 熔断状态仅存 Redis(ADR-013: 多子进程共享,key 过期 = 自动半开)

ADR-013 熔断器语义:
  key:   harness:circuit:{provider_id}
  value: JSON {"failures": N, "opened_at": ts, "last_error": "..."}
  TTL:   CIRCUIT_BREAKER_RECOVERY_SECONDS (过期后自动半开探测)
  状态机: CLOSED(key 不存在) → OPEN(key 存在且 failures >= THRESHOLD)
          → 探测成功后 DELETE key

Prometheus metrics:
  prism_provider_healthy{provider_id}:  熔断时设 0,恢复设 1
  prism_provider_failover_total:        get_adapter() 切换备用 Provider 时 +1

Usage stub:
  record_usage() 打 log + Prometheus,HTTP 回调 stub 指向
  {BACKEND_URL}/internal/callback/usage (DOC-07 Task 7.3 实现接收端)
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

# Use structlog if available (Executor environment), fallback to stdlib logging
try:
    import structlog
    logger = structlog.get_logger(__name__)
    _STRUCTLOG = True
except ImportError:
    logger = logging.getLogger(__name__)  # type: ignore[assignment]
    _STRUCTLOG = False


def _log(level: str, event: str, **kwargs: object) -> None:
    """Unified log call that works with both structlog and stdlib logging."""
    if _STRUCTLOG:
        getattr(logger, level)(event, **kwargs)
    else:
        msg = event + (" " + " ".join(f"{k}={v}" for k, v in kwargs.items()) if kwargs else "")
        getattr(logger, level)(msg)


# ---------------------------------------------------------------------------
# ProviderConfig — ProviderManager 接受的配置(已解密的明文 API Key)
# ---------------------------------------------------------------------------

@dataclass
class ProviderConfig:
    """单个 Provider 的运行时配置.

    所有字段均为已解密后的明文值,由 Backend 在子进程启动前注入。
    ProviderManager 不负责任何解密操作。
    """
    provider_id: str
    name: str
    protocol: str                   # "anthropic" | "openai"
    base_url: str
    api_key: str                    # 已解密的明文 API Key (Backend 侧解密后传入)
    model_id: str
    is_default: bool = False
    priority: int = 0
    is_healthy: bool = True
    capabilities: dict = field(default_factory=dict)  # 从 config.capabilities 取出


# ---------------------------------------------------------------------------
# ProviderManager
# ---------------------------------------------------------------------------

class ProviderManager:
    """Provider 选择 + 故障转移 + 熔断器 + 用量记录.

    Args:
        providers:          ProviderConfig 列表(已解密 API Key,不含 ORM 对象)
        redis_client:       已连接的 redis.Redis 实例(或兼容的 mock)
        failure_threshold:  连续失败 N 次触发熔断 (CIRCUIT_BREAKER_THRESHOLD)
        recovery_seconds:   熔断器 Redis key TTL (CIRCUIT_BREAKER_RECOVERY_SECONDS)
        backend_url:        Backend 回调 URL(可选,未设置时 record_usage 只打 log)
        callback_secret:    回调签名密钥(CALLBACK_SECRET,独立于 JWT_SECRET)
    """

    def __init__(
        self,
        providers: list[ProviderConfig],
        redis_client,
        failure_threshold: int = 3,
        recovery_seconds: int = 300,
        backend_url: Optional[str] = None,
        callback_secret: Optional[str] = None,
    ) -> None:
        self._providers: list[ProviderConfig] = providers
        self._redis = redis_client
        self._failure_threshold = failure_threshold
        self._recovery_seconds = recovery_seconds
        self._backend_url = backend_url or os.environ.get("BACKEND_URL", "")
        self._callback_secret = callback_secret or os.environ.get("CALLBACK_SECRET", "")

    # -----------------------------------------------------------------------
    # get_adapter — 选择可用的 ModelAdapter 实例
    # -----------------------------------------------------------------------

    async def get_adapter(self):
        """获取当前可用的 ModelAdapter 实例.

        选择策略:
          1. 优先选 is_default=True 且熔断器 CLOSED 的 Provider
          2. 若默认 Provider 熔断,按 priority 降序选择第一个 CLOSED Provider
          3. 若切换了 Provider,记录 prism_provider_failover_total +1
          4. 全部熔断时抛出 RuntimeError

        Returns:
            (provider_config, ModelAdapter) 元组
        """
        # 按 is_default=True 优先、priority 降序排序
        sorted_providers = sorted(
            self._providers,
            key=lambda p: (not p.is_default, -p.priority),
        )

        preferred_id = sorted_providers[0].provider_id if sorted_providers else None
        selected: Optional[ProviderConfig] = None

        for provider in sorted_providers:
            if not await self._is_circuit_open(provider.provider_id):
                selected = provider
                break

        if selected is None:
            raise RuntimeError(
                "All providers are circuit-broken. "
                "No healthy provider available for model requests."
            )

        # 记录故障转移事件
        if preferred_id and selected.provider_id != preferred_id:
            _log("warning", "provider_manager.failover",
                 from_provider=preferred_id, to_provider=selected.provider_id)
            self._record_failover_metric(
                from_provider=preferred_id,
                to_provider=selected.provider_id,
            )

        adapter = self._build_adapter(selected)
        return selected, adapter

    # -----------------------------------------------------------------------
    # record_success — 重置熔断计数
    # -----------------------------------------------------------------------

    async def record_success(self, provider_id: str) -> None:
        """记录成功调用,重置该 Provider 的熔断状态.

        ADR-013: 成功后 DELETE Redis key,熔断器回到 CLOSED 状态。
        """
        redis_key = f"harness:circuit:{provider_id}"
        existing = self._redis.get(redis_key)
        if existing:
            self._redis.delete(redis_key)
            _log("info", "provider_manager.circuit_recovered", provider_id=provider_id)
            self._set_provider_healthy_metric(provider_id, healthy=True)

    # -----------------------------------------------------------------------
    # record_failure — 累计失败,达阈值触发熔断
    # -----------------------------------------------------------------------

    async def record_failure(self, provider_id: str, error: str) -> None:
        """记录失败调用.连续失败达阈值时写 Redis key(触发熔断) + Prometheus + 上报 harness_event.

        ADR-013:
          - key: harness:circuit:{provider_id}
          - value: JSON {"failures": N, "opened_at": ts, "last_error": "..."}
          - TTL: CIRCUIT_BREAKER_RECOVERY_SECONDS
          - 触发熔断时 Prometheus prism_provider_healthy 设 0
        """
        redis_key = f"harness:circuit:{provider_id}"
        raw = self._redis.get(redis_key)

        if raw:
            state = json.loads(raw)
        else:
            state = {"failures": 0, "opened_at": None, "last_error": ""}

        state["failures"] = state.get("failures", 0) + 1
        state["last_error"] = error

        if state["failures"] >= self._failure_threshold and not state.get("opened_at"):
            # 触发熔断
            state["opened_at"] = time.time()
            _log("error", "provider_manager.circuit_opened",
                 provider_id=provider_id, failures=state["failures"], error=error)
            self._set_provider_healthy_metric(provider_id, healthy=False)
            # 上报 harness_event (stub — DOC-07 Task 7.3 实现接收端)
            await self._report_harness_event(
                event_type="harness.circuit_break",
                provider_id=provider_id,
                payload={"failures": state["failures"], "error": error},
            )
        else:
            _log("warning", "provider_manager.failure_recorded",
                 provider_id=provider_id, failures=state["failures"],
                 threshold=self._failure_threshold, error=error)

        self._redis.setex(
            redis_key,
            self._recovery_seconds,
            json.dumps(state),
        )

    # -----------------------------------------------------------------------
    # record_usage — 用量记录 stub
    # -----------------------------------------------------------------------

    async def record_usage(
        self,
        provider_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_hit_tokens: int = 0,
        cache_creation_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        """记录 token 用量.

        本 Task 实现为 stub:
          - 打 log
          - 更新 Prometheus prism_model_tokens_total
          - 若配置了 BACKEND_URL,发 HTTP POST 到 /internal/callback/usage
            (DOC-07 Task 7.3 实现接收端,现在 501)

        进程边界: 不 import backend.* / SQLAlchemy;DB 写入通过 HTTP 回调完成。
        """
        _log("info", "provider_manager.usage",
             provider_id=provider_id, model=model,
             input_tokens=input_tokens, output_tokens=output_tokens,
             cache_hit_tokens=cache_hit_tokens,
             cache_creation_tokens=cache_creation_tokens, cost_usd=cost_usd)

        # Prometheus metrics
        self._record_token_metrics(
            provider_id=provider_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_hit_tokens=cache_hit_tokens,
            cache_creation_tokens=cache_creation_tokens,
        )

        # HTTP 回调 stub (DOC-07 Task 7.3 实现接收端)
        if self._backend_url:
            await self._post_usage_callback(
                provider_id=provider_id,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_hit_tokens=cache_hit_tokens,
                cache_creation_tokens=cache_creation_tokens,
                cost_usd=cost_usd,
            )

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    async def _is_circuit_open(self, provider_id: str) -> bool:
        """ADR-013: Redis key 存在且 failures >= threshold → OPEN。key 不存在 → CLOSED。"""
        redis_key = f"harness:circuit:{provider_id}"
        raw = self._redis.get(redis_key)
        if not raw:
            return False  # CLOSED
        state = json.loads(raw)
        return state.get("failures", 0) >= self._failure_threshold

    def _build_adapter(self, config: ProviderConfig):
        """根据 protocol 构建对应的 ModelAdapter 实例.

        进程边界: executor/adapters/*.py 不 import backend.app.*
        """
        from executor.adapters.base import ProviderCapabilities
        from executor.adapters.anthropic_driver import AnthropicDriver
        from executor.adapters.openai_driver import OpenAIDriver

        caps_dict = config.capabilities or {}
        capabilities = ProviderCapabilities(
            prompt_cache=caps_dict.get("prompt_cache", False),
            streaming_tools=caps_dict.get("streaming_tools", True),
            extended_thinking=caps_dict.get("extended_thinking", False),
            vision=caps_dict.get("vision", False),
        )

        if config.protocol == "anthropic":
            return AnthropicDriver(
                base_url=config.base_url,
                api_key=config.api_key,
                model=config.model_id,
                capabilities=capabilities,
            )
        elif config.protocol == "openai":
            return OpenAIDriver(
                base_url=config.base_url,
                api_key=config.api_key,
                model=config.model_id,
                capabilities=capabilities,
            )
        else:
            raise ValueError(
                f"Unknown protocol '{config.protocol}' for provider {config.provider_id}. "
                "Supported: 'anthropic', 'openai'"
            )

    def _set_provider_healthy_metric(self, provider_id: str, healthy: bool) -> None:
        """更新 prism_provider_healthy Gauge (ADR-013 + DOC-12 ADR-116)."""
        try:
            # Executor 侧不持有 backend metrics,尝试导入;失败则 log-only
            from executor.observability.metrics import prism_provider_healthy as _gauge
            _gauge.labels(provider_id=provider_id).set(1 if healthy else 0)
        except ImportError:
            pass  # metrics 模块不可用时静默降级
        except Exception as exc:
            _log("debug", "provider_manager.metric_error", exc=str(exc))

    def _record_failover_metric(self, from_provider: str, to_provider: str) -> None:
        """记录 prism_provider_failover_total Counter."""
        try:
            from executor.observability.metrics import prism_provider_failover_total as _ctr
            _ctr.labels(
                from_provider=from_provider, to_provider=to_provider
            ).inc()
        except ImportError:
            pass
        except Exception as exc:
            _log("debug", "provider_manager.metric_error", exc=str(exc))

    def _record_token_metrics(
        self,
        provider_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_hit_tokens: int,
        cache_creation_tokens: int,
    ) -> None:
        """更新 prism_model_tokens_total Counter."""
        try:
            from executor.observability.metrics import prism_model_tokens_total as _ctr
            _ctr.labels(provider=provider_id, model=model, token_type="input").inc(input_tokens)
            _ctr.labels(provider=provider_id, model=model, token_type="output").inc(output_tokens)
            if cache_hit_tokens:
                _ctr.labels(provider=provider_id, model=model, token_type="cache_read").inc(cache_hit_tokens)
            if cache_creation_tokens:
                _ctr.labels(provider=provider_id, model=model, token_type="cache_write").inc(cache_creation_tokens)
        except ImportError:
            pass
        except Exception as exc:
            _log("debug", "provider_manager.metric_error", exc=str(exc))

    async def _report_harness_event(
        self,
        event_type: str,
        provider_id: str,
        payload: dict,
    ) -> None:
        """向 Backend 上报 harness_event(stub).

        DOC-07 Task 7.3 实现接收端 /internal/callback/harness_event。
        本 Task 仅实现签名逻辑 + POST;接收端 501 是预期行为。

        签名使用 CALLBACK_SECRET(HMAC-SHA256),独立于 JWT_SECRET (ADR-004 三密钥)。
        """
        import hashlib
        import hmac

        if not self._backend_url:
            _log("debug", "provider_manager.harness_event_skip",
                 reason="BACKEND_URL not set", event_type=event_type)
            return

        body = json.dumps({
            "event_type": event_type,
            "provider_id": provider_id,
            "timestamp": time.time(),
            **payload,
        }, separators=(",", ":"))

        signature = hmac.new(
            self._callback_secret.encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    f"{self._backend_url}/internal/callback/harness_event",
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Prism-Signature": signature,
                    },
                )
        except Exception as exc:
            # 回调失败不影响主流程
            _log("debug", "provider_manager.harness_event_failed",
                 event_type=event_type, error=str(exc))

    async def _post_usage_callback(
        self,
        provider_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_hit_tokens: int,
        cache_creation_tokens: int,
        cost_usd: float,
    ) -> None:
        """向 Backend 发送用量回调 stub (DOC-07 Task 7.3 实现接收端)."""
        import hashlib
        import hmac

        body = json.dumps({
            "provider_id": provider_id,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_hit_tokens": cache_hit_tokens,
            "cache_creation_tokens": cache_creation_tokens,
            "cost_usd": cost_usd,
            "timestamp": time.time(),
        }, separators=(",", ":"))

        signature = hmac.new(
            self._callback_secret.encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    f"{self._backend_url}/internal/callback/usage",
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Prism-Signature": signature,
                    },
                )
                # 501 是预期的(DOC-07 Task 7.3 未实现接收端)
                if resp.status_code not in (200, 201, 204, 501):
                    _log("warning", "provider_manager.usage_callback_unexpected",
                         status_code=resp.status_code)
        except Exception as exc:
            # 回调失败不影响主流程
            _log("debug", "provider_manager.usage_callback_failed", error=str(exc))
