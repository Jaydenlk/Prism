"""
Prism v2 — Provider Service (DOC-02 Task 2.3)

ADR-010: scope 二值权限矩阵
  - scope='system': 全局预设,user_id IS NULL,所有用户可见
  - scope='user':   用户私有,user_id 必须匹配当前用户

ADR-011: config.capabilities 强制字段 — Service 层二次校验

ADR-012: API Key 用 AES-256-GCM(ENCRYPTION_KEY) 加密存储,响应中只返回掩码

ADR-013: 熔断状态仅存 Redis (ProviderManager 负责),Service 层只管 CRUD

Bootstrap: bootstrap_presets() 幂等注册 scope='system' 内置预设
"""
from __future__ import annotations


import structlog

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decrypt_value, encrypt_value
from app.models.provider import Provider
from app.schemas.provider import (
    CreateProviderRequest,
    ProviderCapabilitiesSchema,
    ProviderPreset,
    ProviderResponse,
    TestProviderResponse,
    UpdateProviderRequest,
    _mask_key,
)
from app.services.provider_presets import BUILTIN_PRESETS, PRESET_ENV_MAP

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# ProviderService
# ---------------------------------------------------------------------------

class ProviderService:
    """Provider CRUD + 内置预设注册 + 连通性探测."""

    # --- Public class methods -----------------------------------------------

    @classmethod
    def list_providers(
        cls,
        db: Session,
        user_id: str,
    ) -> list[ProviderResponse]:
        """列出 scope='system' 的全局预设 + 当前用户 scope='user' 的 Provider.

        ADR-010: SELECT WHERE scope='system' OR (scope='user' AND user_id=current)
        """
        rows = (
            db.query(Provider)
            .filter(
                (Provider.scope == "system")
                | ((Provider.scope == "user") & (Provider.user_id == user_id))
            )
            .order_by(Provider.scope.desc(), Provider.priority.desc(), Provider.created_at)
            .all()
        )
        return [cls._to_response(p) for p in rows]

    @classmethod
    def get_provider(
        cls,
        db: Session,
        provider_id: str,
        user_id: str,
    ) -> Provider:
        """获取单个 Provider 并校验访问权限."""
        provider = db.get(Provider, provider_id)
        if provider is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Provider {provider_id} not found.",
            )
        cls._assert_readable(provider, user_id)
        return provider

    @classmethod
    def create_provider(
        cls,
        db: Session,
        user_id: str,
        data: CreateProviderRequest,
    ) -> ProviderResponse:
        """创建用户私有 Provider (scope='user').

        - API Key 使用 ENCRYPTION_KEY(AES-256-GCM) 加密 (ADR-012)
        - is_default=True 时,先将该用户的其他 Provider.is_default 置 False
        - config.capabilities 已在 Pydantic 层校验,此处二次确认
        """
        # ADR-011 二次校验(防御性编程,Pydantic 已验过)
        if "capabilities" not in data.config:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="config.capabilities is required.",
            )

        # 若设为默认,先清除该用户其他默认
        if data.is_default:
            cls._clear_user_defaults(db, user_id)

        # AES-256-GCM 加密 API Key (ADR-012)
        encrypted_key = encrypt_value(data.api_key, settings.ENCRYPTION_KEY)

        provider = Provider(
            scope="user",
            user_id=user_id,
            name=data.name,
            protocol=data.protocol,
            base_url=data.base_url.rstrip("/"),
            api_key_encrypted=encrypted_key,
            model_id=data.model_id,
            is_default=data.is_default,
            priority=data.priority,
            is_healthy=True,
            config=data.config,
        )
        db.add(provider)
        db.commit()
        db.refresh(provider)

        logger.info(
            "provider.created",
            provider_id=provider.id,
            user_id=user_id,
            name=provider.name,
        )
        return cls._to_response(provider)

    @classmethod
    def update_provider(
        cls,
        db: Session,
        user_id: str,
        provider_id: str,
        data: UpdateProviderRequest,
        is_admin: bool = False,
    ) -> ProviderResponse:
        """更新 Provider.

        权限矩阵 (ADR-010):
          - scope='user': 只能改 user_id == current_user 的记录
          - scope='system': 仅 admin 可改
        """
        provider = db.get(Provider, provider_id)
        if provider is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Provider {provider_id} not found.",
            )

        cls._assert_writable(provider, user_id, is_admin)

        if data.name is not None:
            provider.name = data.name

        if data.api_key is not None:
            provider.api_key_encrypted = encrypt_value(
                data.api_key, settings.ENCRYPTION_KEY
            )

        if data.is_default is not None:
            if data.is_default and not provider.is_default:
                cls._clear_user_defaults(db, user_id)
            provider.is_default = data.is_default

        if data.priority is not None:
            provider.priority = data.priority

        if data.config is not None:
            if "capabilities" not in data.config:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="config.capabilities is required when updating config.",
                )
            provider.config = data.config

        db.commit()
        db.refresh(provider)

        logger.info(
            "provider.updated",
            provider_id=provider_id,
            user_id=user_id,
        )
        return cls._to_response(provider)

    @classmethod
    def delete_provider(
        cls,
        db: Session,
        user_id: str,
        provider_id: str,
        is_admin: bool = False,
    ) -> None:
        """删除 Provider.

        权限矩阵同 update_provider (ADR-010).
        """
        provider = db.get(Provider, provider_id)
        if provider is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Provider {provider_id} not found.",
            )

        cls._assert_writable(provider, user_id, is_admin)

        db.delete(provider)
        db.commit()

        logger.info(
            "provider.deleted",
            provider_id=provider_id,
            user_id=user_id,
        )

    @classmethod
    async def test_provider(
        cls,
        db: Session,
        user_id: str,
        provider_id: str,
    ) -> TestProviderResponse:
        """探测 Provider 连通性 + 能力检测 (ADR-011).

        流程:
          1. 解密 API Key (ENCRYPTION_KEY)
          2. 发送最小请求探测连通性 + prompt_cache 支持
          3. 返回 detected_capabilities 供用户参考
        """
        import time


        provider = db.get(Provider, provider_id)
        if provider is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Provider {provider_id} not found.",
            )

        cls._assert_readable(provider, user_id)

        # 解密 API Key (ADR-012: 解密在 Backend 侧)
        try:
            api_key = decrypt_value(provider.api_key_encrypted, settings.ENCRYPTION_KEY)
        except Exception as exc:
            return TestProviderResponse(
                success=False,
                error=f"Failed to decrypt API key: {exc}",
            )

        start_ms = int(time.monotonic() * 1000)

        try:
            detected = await cls._probe_capabilities(
                base_url=provider.base_url,
                api_key=api_key,
                model_id=provider.model_id,
                protocol=provider.protocol,
            )
            latency_ms = int(time.monotonic() * 1000) - start_ms

            logger.info(
                "provider.test_success",
                provider_id=provider_id,
                latency_ms=latency_ms,
            )
            return TestProviderResponse(
                success=True,
                latency_ms=latency_ms,
                detected_capabilities=detected,
            )

        except Exception as exc:
            latency_ms = int(time.monotonic() * 1000) - start_ms
            logger.warning(
                "provider.test_failed",
                provider_id=provider_id,
                error=str(exc),
            )
            return TestProviderResponse(
                success=False,
                latency_ms=latency_ms,
                error=str(exc),
            )

    @classmethod
    def list_providers_with_health(
        cls,
        db: Session,
        user_id: str,
        redis_client,
    ) -> list[ProviderResponse]:
        """列出 Provider 并从 Redis 合并实时熔断状态.

        ADR-013: ProviderManager 将熔断状态写入 Redis key
                 `harness:circuit:{provider_id}` (JSON, TTL 设为 5 min)。
        Backend 以 Redis 为准: key 存在 → is_healthy=False (熔断中)。

        注意: redis_client 可以是 sync (redis.Redis) 或 async (redis.asyncio.Redis)。
              路由层传入 sync 包装版或在调用前 await。此处使用同步 .get()。
        """
        providers = cls.list_providers(db=db, user_id=user_id)
        for p in providers:
            circuit_key = f"harness:circuit:{p.id}"
            try:
                circuit_data = redis_client.get(circuit_key)
                if circuit_data:
                    p.is_healthy = False
                else:
                    p.is_healthy = True
            except Exception as exc:
                # Redis 不可用时降级: 保持 DB 中的 is_healthy 值
                logger.warning(
                    "provider.health_check.redis_error",
                    provider_id=p.id,
                    error=str(exc),
                )
        return providers

    @classmethod
    def get_presets(cls) -> list[ProviderPreset]:
        """返回内置 Provider 预设列表 (ADR-011: 每个预设带 capabilities)."""
        return BUILTIN_PRESETS

    @classmethod
    def bootstrap_presets(cls, db: Session) -> int:
        """幂等注册内置预设为 scope='system' 记录.

        规则:按 (name, scope='system') 查询 — 已存在则跳过,不存在则 INSERT。
        返回本次新增的记录数。

        ADR-010: bootstrap 的预设 scope='system', user_id=NULL
        """
        inserted = 0
        for preset in BUILTIN_PRESETS:
            existing = (
                db.query(Provider)
                .filter(Provider.scope == "system", Provider.name == preset.name)
                .first()
            )
            if existing is not None:
                logger.debug(
                    "provider.bootstrap_skip",
                    name=preset.name,
                    reason="already exists",
                )
                continue

            # 读 .env 提供的默认 API Key / base_url（管理员后续可在 UI 改）
            # 空 key → 占位符，用户/管理员未配置时该 Provider 不可用
            env_map = PRESET_ENV_MAP.get(preset.name, {})
            env_api_key = getattr(settings, env_map.get("api_key", ""), "") if env_map else ""
            env_base_url = getattr(settings, env_map.get("base_url", ""), "") if env_map else ""
            env_model_id = getattr(settings, env_map.get("model_id", ""), "") if env_map else ""
            real_key = env_api_key.strip() if env_api_key else ""
            key_value = real_key if real_key else "SYSTEM_PRESET_NO_KEY"
            api_key_encrypted = encrypt_value(key_value, settings.ENCRYPTION_KEY)
            base_url_final = (env_base_url or preset.base_url).rstrip("/")
            model_id_final = (env_model_id.strip() if env_model_id else "") or preset.model_id

            provider = Provider(
                scope="system",
                user_id=None,
                name=preset.name,
                protocol=preset.protocol,
                base_url=base_url_final,
                api_key_encrypted=api_key_encrypted,
                model_id=model_id_final,
                is_default=False,
                priority=0,
                is_healthy=bool(real_key),
                config={"capabilities": preset.capabilities.model_dump()},
            )
            db.add(provider)
            inserted += 1
            logger.info(
                "provider.bootstrap_insert",
                name=preset.name,
                protocol=preset.protocol,
            )

        if inserted > 0:
            db.commit()

        logger.info(
            "provider.bootstrap_complete",
            total_presets=len(BUILTIN_PRESETS),
            inserted=inserted,
        )
        return inserted

    # --- Private helpers ----------------------------------------------------

    @classmethod
    def _to_response(cls, provider: Provider) -> ProviderResponse:
        """将 ORM Provider 对象转换为 ProviderResponse.

        ADR-012: api_key_masked 通过 _mask_key() 生成,永不包含明文。
        解密 api_key_encrypted 仅为生成掩码 — 只取首尾字符,不暴露完整值。
        """
        # 尝试解密只取首尾做掩码;若解密失败(如占位符)直接返回 ***
        try:
            plaintext = decrypt_value(provider.api_key_encrypted, settings.ENCRYPTION_KEY)
            masked = _mask_key(plaintext)
        except Exception:
            masked = "***"

        return ProviderResponse(
            id=provider.id,
            scope=provider.scope,
            name=provider.name,
            protocol=provider.protocol,
            base_url=provider.base_url,
            api_key_masked=masked,
            model_id=provider.model_id,
            is_default=provider.is_default,
            priority=provider.priority,
            is_healthy=provider.is_healthy,
            config=provider.config,
            user_id=provider.user_id,
            created_at=provider.created_at,
            updated_at=provider.updated_at,
        )

    @classmethod
    def _assert_readable(cls, provider: Provider, user_id: str) -> None:
        """确认当前用户可以读取该 Provider.

        scope='system': 所有人可读
        scope='user': 只有 owner 可读
        """
        if provider.scope == "system":
            return
        if provider.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this provider.",
            )

    @classmethod
    def _assert_writable(
        cls, provider: Provider, user_id: str, is_admin: bool
    ) -> None:
        """确认当前用户可以修改/删除该 Provider.

        ADR-010 权限矩阵:
          scope='system': require_admin
          scope='user':   user_id == current_user
        """
        if provider.scope == "system":
            if not is_admin:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Administrator privileges required to modify system providers.",
                )
            return
        # scope='user'
        if provider.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to modify this provider.",
            )

    @classmethod
    def _clear_user_defaults(cls, db: Session, user_id: str) -> None:
        """将该用户所有 Provider 的 is_default 置 False."""
        (
            db.query(Provider)
            .filter(Provider.scope == "user", Provider.user_id == user_id)
            .update({"is_default": False})
        )

    @classmethod
    async def _probe_capabilities(
        cls,
        base_url: str,
        api_key: str,
        model_id: str,
        protocol: str,
    ) -> ProviderCapabilitiesSchema:
        """向 Provider 发送最小探测请求,检测能力.

        探测策略 (ADR-011):
          - 发送带 cache_control 的请求,观察响应中是否有 cache_read_input_tokens → prompt_cache
          - 观察响应格式确认 streaming_tools 支持(保守默认 True)
          - vision / extended_thinking 保守默认 False(需人工确认或专项探测)

        注意:探测请求使用真实 API,若 API Key 无效将抛出异常。
        """
        import httpx

        capabilities = ProviderCapabilitiesSchema(
            prompt_cache=False,
            streaming_tools=True,   # 大多数现代模型支持
            extended_thinking=False,
            vision=False,
        )

        headers = {
            "Content-Type": "application/json",
        }

        base = base_url.rstrip("/")

        if protocol == "anthropic":
            headers["x-api-key"] = api_key
            headers["anthropic-version"] = "2023-06-01"
            # 使用 cache_control 探测 prompt_cache 支持
            payload = {
                "model": model_id,
                "max_tokens": 5,
                "system": [
                    {
                        "type": "text",
                        "text": "You are a test probe.",
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                "messages": [{"role": "user", "content": "ping"}],
            }
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(f"{base}/v1/messages", json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                usage = data.get("usage", {})
                # 有 cache_read_input_tokens 字段 → 支持 prompt_cache
                if "cache_read_input_tokens" in usage or "cache_creation_input_tokens" in usage:
                    capabilities.prompt_cache = True

        else:  # protocol == "openai"
            headers["Authorization"] = f"Bearer {api_key}"
            payload = {
                "model": model_id,
                "max_tokens": 5,
                "messages": [{"role": "user", "content": "ping"}],
                "stream": False,
            }
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(f"{base}/chat/completions", json=payload, headers=headers)
                resp.raise_for_status()
                # OpenAI 兼容接口不支持 prompt_cache(Anthropic 专属)
                capabilities.prompt_cache = False

        return capabilities
