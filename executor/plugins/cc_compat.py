"""
CC 插件格式适配器

DOC-05 Task 5.7: CC 兼容层（ConversionReport）（ADR-054/ADR-055）

加载逻辑：
1. 检测插件目录中是否存在 plugin.json（CC 格式）或 plugin.yaml（Prism 格式）
2. plugin.json → 转换为 Prism PluginConfig（兼容加载）
3. plugin.yaml → 直接加载为 Prism PluginConfig（Pydantic 严格校验，缺字段抛
   PluginSchemaError，调用方可转为 HTTP 422）
4. 两者都存在 → 优先使用 plugin.yaml（Prism 格式更完整，ADR-054 决策）
5. 都不存在但有 skills/ 目录 → 作为纯 Skills 集合加载
6. 都不存在且无 skills/ → PluginFormatError

转换规则（plugin.json → PluginConfig）：
- name, description, version → 直接映射
- skills/ 目录存在 → skills_dir = ./skills
- hooks/ 目录存在 → hooks_config keys 记录（具体 handler 列表从目录扫描）
- mcp-servers/ 目录存在 → mcp_servers stub（Phase 1 不读取内容，记录 lost_fields）
- CC 没有 vertical_tuning / harness_overrides 概念 → agent_overrides 留空

export_to_cc 转换规则（PluginConfig → CC plugin.json）：
- prism.vertical_tuning → lost_fields（CC 不支持）
- prism.harness_overrides → lost_fields（CC 不支持）
- mcp_servers → mcp-servers/ 目录条目（若 name 冲突则写 warnings）
- skills_dir → skills/ 目录（原样复制路径引用，zip 中保留目录结构注释）

ADR-054（PRD 原标 ADR-050-A 平移）:
    export_to_cc 返回 ConversionReport（含 cc_compat_zip / lost_fields / warnings /
    cc_plugin_json），而非直接写文件。调用方决定落盘/上传。

ADR-055（PRD 原标 ADR-050-B 平移）:
    plugin.yaml 用 Pydantic schema 严格校验；缺字段抛 PluginSchemaError（HTTP 422）；
    未识别字段警告不拒绝（forward-compat）。

进程边界：本模块只 import 标准库 + executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

import structlog

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# 异常类型
# ---------------------------------------------------------------------------


class PluginFormatError(ValueError):
    """无法识别插件格式（plugin_dir 中没有 plugin.yaml / plugin.json / skills/）。"""


class PluginSchemaError(ValueError):
    """plugin.yaml 校验失败（缺必填字段或字段类型错误）。

    ADR-055：调用方（Backend API）应将此异常转为 HTTP 422 + 详细错误位置。
    errors 字段包含与 Pydantic ValidationError 格式对齐的错误列表。
    """

    def __init__(self, message: str, errors: list[dict] | None = None) -> None:
        super().__init__(message)
        self.errors: list[dict] = errors or []


# ---------------------------------------------------------------------------
# ConversionReport（ADR-054）
# ---------------------------------------------------------------------------


@dataclass
class ConversionReport:
    """CC 导出返回结构化报告而非直接写文件（ADR-054）。

    调用方决定是否把 cc_compat_zip 落盘或上传；不得静默成功（PRD 明确禁止）。

    字段：
        success:        整体是否成功（即使有 warnings，只要 lost_fields 不含
                        关键字段也视为成功；若 export 过程出错则 False）
        cc_compat_zip:  CC 格式目录的 zip 字节（可直接写文件）
        lost_fields:    转换丢弃的 Prism 扩展字段清单（如 "prism.vertical_tuning"）
        warnings:       转换过程的告警（如 MCP 名称冲突、hooks_dir 为空）
        plugin_name:    Plugin 名称（便于调用方 log）
        cc_plugin_json: 生成的 plugin.json 内容（dict，供调用方二次处理）
    """

    success: bool
    cc_compat_zip: bytes
    lost_fields: list[str]
    warnings: list[str]
    plugin_name: str
    cc_plugin_json: dict


# ---------------------------------------------------------------------------
# Pydantic schema（ADR-055）— plugin.yaml 严格校验
# ---------------------------------------------------------------------------

try:
    from pydantic import BaseModel as _PydanticBase
    from pydantic import Field as _Field
    from pydantic import ValidationError as _ValidationError
    from pydantic import model_validator as _model_validator

    _PYDANTIC_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PYDANTIC_AVAILABLE = False
    _PydanticBase = object  # type: ignore[assignment,misc]
    _Field = None  # type: ignore[assignment]
    _ValidationError = None  # type: ignore[assignment]
    _model_validator = None  # type: ignore[assignment]


if _PYDANTIC_AVAILABLE:

    class _PrismMcpServer(_PydanticBase):  # type: ignore[misc]
        """单个 MCP Server 配置（plugin.yaml prism.mcp_servers 列表项）。"""

        name: str = _Field(..., description="MCP Server 唯一名称")
        command: str = _Field(..., description="启动命令（如 npx / python）")
        args: list[str] = _Field(default_factory=list)
        env: dict[str, str] = _Field(default_factory=dict)

        model_config = {"extra": "allow"}  # forward-compat: 未知字段警告不拒绝

    class _PrismExtension(_PydanticBase):  # type: ignore[misc]
        """plugin.yaml 的 prism: 扩展块（CC 插件不包含此块）。"""

        vertical_tuning: dict = _Field(default_factory=dict)
        harness_overrides: dict = _Field(default_factory=dict)
        mcp_servers: list[_PrismMcpServer] = _Field(default_factory=list)
        dependencies: dict = _Field(default_factory=dict)

        model_config = {"extra": "allow"}

    class PluginYamlSchema(_PydanticBase):  # type: ignore[misc]
        """plugin.yaml 的 Pydantic 严格校验 schema（ADR-055）。

        必填字段：name（缺失抛 PluginSchemaError → HTTP 422）。
        未识别字段：extra="allow" 策略——收集后警告（不拒绝，便于 forward-compat）。
        """

        name: str = _Field(..., min_length=1, description="Plugin 唯一名称（必填）")
        description: str = _Field(default="", description="Plugin 功能描述")
        version: str = _Field(default="1.0.0", description="版本号（SemVer）")
        author: str = _Field(default="", description="作者")
        skills_dir: str = _Field(default="", description="Plugin 内 skills/ 目录相对路径")
        hooks_dir: str = _Field(default="", description="Plugin 内 hooks/ 目录相对路径")
        prism: _PrismExtension = _Field(default_factory=_PrismExtension)

        model_config = {"extra": "allow"}

        def extra_field_names(self) -> list[str]:
            """返回未在 schema 中定义的额外字段名（forward-compat 告警用）。"""
            known = set(self.model_fields.keys())  # type: ignore[attr-defined]
            all_keys = set(self.model_dump().keys())  # type: ignore[attr-defined]
            return sorted(all_keys - known)

else:  # pragma: no cover

    class PluginYamlSchema:  # type: ignore[no-redef]
        """Fallback（pydantic 不可用）。"""

        def __init__(self, **kwargs: object) -> None:
            self.name: str = str(kwargs.get("name", ""))
            self.description: str = str(kwargs.get("description", ""))
            self.version: str = str(kwargs.get("version", "1.0.0"))
            self.author: str = str(kwargs.get("author", ""))
            self.skills_dir: str = str(kwargs.get("skills_dir", ""))
            self.hooks_dir: str = str(kwargs.get("hooks_dir", ""))
            self.prism: object = kwargs.get("prism", {})

        def extra_field_names(self) -> list[str]:
            return []


# ---------------------------------------------------------------------------
# CCPluginAdapter
# ---------------------------------------------------------------------------


class CCPluginAdapter:
    """CC 插件格式适配器（ADR-054/ADR-055）。

    统一入口：detect_format → load / export_to_cc。

    线程安全：无可变状态，实例可复用。
    """

    # ------------------------------------------------------------------
    # 格式检测
    # ------------------------------------------------------------------

    def detect_format(
        self, plugin_dir: str
    ) -> Literal["cc", "prism", "skills_only", "unknown"]:
        """检测插件目录格式。

        优先级（ADR-054）：
          1. plugin.yaml 存在 → "prism"（Prism 格式更完整，覆盖 CC 格式）
          2. plugin.json 存在 → "cc"
          3. skills/ 子目录存在 → "skills_only"
          4. 以上都不满足 → "unknown"
        """
        if os.path.isfile(os.path.join(plugin_dir, "plugin.yaml")):
            return "prism"
        if os.path.isfile(os.path.join(plugin_dir, "plugin.json")):
            return "cc"
        if os.path.isdir(os.path.join(plugin_dir, "skills")):
            return "skills_only"
        return "unknown"

    # ------------------------------------------------------------------
    # 统一加载入口
    # ------------------------------------------------------------------

    def load(self, plugin_dir: str) -> "PluginConfig":
        """统一加载入口：自动检测格式并转换为 PluginConfig。

        抛出：
            PluginFormatError — 格式无法识别（"unknown"）
            PluginSchemaError — plugin.yaml 必填字段缺失（ADR-055，调用方转 422）
        """
        fmt = self.detect_format(plugin_dir)
        if fmt == "prism":
            return self._load_prism_plugin(plugin_dir)
        elif fmt == "cc":
            return self._load_cc_plugin(plugin_dir)
        elif fmt == "skills_only":
            return self._load_skills_collection(plugin_dir)
        else:
            raise PluginFormatError(f"无法识别插件格式: {plugin_dir}")

    # ------------------------------------------------------------------
    # Prism 原生格式加载（ADR-055 严格校验）
    # ------------------------------------------------------------------

    def _load_prism_plugin(self, plugin_dir: str) -> "PluginConfig":
        """加载 Prism 原生 plugin.yaml，Pydantic 严格校验（ADR-055）。

        成功：返回 PluginConfig（prism.mcp_servers / vertical_tuning 等均映射）。
        失败：抛 PluginSchemaError（调用方 Backend API 转 HTTP 422）。
        未识别字段：写 structlog WARNING（不拒绝，forward-compat）。
        """
        yaml_path = os.path.join(plugin_dir, "plugin.yaml")
        raw = self._read_yaml(yaml_path)

        # Pydantic 验证（ADR-055）
        schema = self._validate_plugin_yaml(raw, yaml_path)

        # 处理 prism 扩展块
        prism_ext = schema.prism if hasattr(schema, "prism") else None

        # 提取 mcp_servers
        mcp_servers: list[dict] = []
        if prism_ext and hasattr(prism_ext, "mcp_servers"):
            for srv in prism_ext.mcp_servers:
                if hasattr(srv, "model_dump"):
                    mcp_servers.append(srv.model_dump())  # type: ignore[attr-defined]
                elif isinstance(srv, dict):
                    mcp_servers.append(srv)

        # hooks_config：从 hooks_dir 目录推断（Phase 1 仅记录目录存在）
        hooks_config: dict = {}
        hooks_dir_rel = getattr(schema, "hooks_dir", "") or ""
        if hooks_dir_rel:
            hooks_abs = os.path.join(plugin_dir, hooks_dir_rel)
            if os.path.isdir(hooks_abs):
                hooks_config = self._scan_hooks_dir(hooks_abs)

        # agent_overrides：来自 prism.vertical_tuning
        agent_overrides: dict = {}
        if prism_ext and hasattr(prism_ext, "vertical_tuning"):
            vt = prism_ext.vertical_tuning
            if isinstance(vt, dict) and vt:
                agent_overrides["vertical_tuning"] = vt
        if prism_ext and hasattr(prism_ext, "harness_overrides"):
            ho = prism_ext.harness_overrides
            if isinstance(ho, dict) and ho:
                agent_overrides["harness_overrides"] = ho

        # 未识别字段警告
        extra = schema.extra_field_names() if hasattr(schema, "extra_field_names") else []
        if extra:
            logger.warning(
                "plugin.yaml.unknown_fields",
                plugin=schema.name,
                unknown_fields=extra,
                forward_compat=True,
            )

        from executor.plugins.plugin_types import PluginConfig

        config = PluginConfig(
            name=schema.name,
            description=getattr(schema, "description", ""),
            version=getattr(schema, "version", "1.0.0"),
            skills_dir=os.path.join(plugin_dir, schema.skills_dir) if schema.skills_dir else "",
            hooks_config=hooks_config,
            mcp_servers=mcp_servers,
            agent_overrides=agent_overrides,
            plugin_root=plugin_dir,
        )

        logger.info(
            "plugin.loaded_prism",
            plugin=schema.name,
            plugin_dir=plugin_dir,
            mcp_count=len(mcp_servers),
            has_hooks=bool(hooks_config),
        )
        return config

    # ------------------------------------------------------------------
    # CC 格式加载（plugin.json → PluginConfig）
    # ------------------------------------------------------------------

    def _load_cc_plugin(self, plugin_dir: str) -> "PluginConfig":
        """将 CC plugin.json 转换为 Prism PluginConfig。

        CC plugin.json 字段映射：
          name, description, version → 直接映射
          skills/ 目录存在 → skills_dir
          hooks/ 目录存在 → hooks_config（扫描 handler 文件）
          mcp-servers/ 目录存在 → mcp_servers stub（Phase 1 记录 name，command 待补）
          CC 没有 vertical_tuning → agent_overrides 留空
        """
        json_path = os.path.join(plugin_dir, "plugin.json")
        with open(json_path, encoding="utf-8") as fh:
            cc_data: dict = json.load(fh)

        name = cc_data.get("name", os.path.basename(plugin_dir))
        description = cc_data.get("description", "")
        version = cc_data.get("version", "1.0.0")

        # skills/ 目录
        skills_dir = ""
        skills_abs = os.path.join(plugin_dir, "skills")
        if os.path.isdir(skills_abs):
            skills_dir = skills_abs

        # hooks/ 目录（CC 格式，目录名与 Prism 相同）
        hooks_config: dict = {}
        hooks_abs = os.path.join(plugin_dir, "hooks")
        if os.path.isdir(hooks_abs):
            hooks_config = self._scan_hooks_dir(hooks_abs)

        # mcp-servers/ 目录（CC 用 "mcp-servers"，Prism 用 "mcp"）
        mcp_servers: list[dict] = []
        for candidate in ("mcp-servers", "mcp"):
            mcp_abs = os.path.join(plugin_dir, candidate)
            if os.path.isdir(mcp_abs):
                mcp_servers = self._scan_mcp_servers_dir(mcp_abs)
                break

        from executor.plugins.plugin_types import PluginConfig

        config = PluginConfig(
            name=name,
            description=description,
            version=version,
            skills_dir=skills_dir,
            hooks_config=hooks_config,
            mcp_servers=mcp_servers,
            agent_overrides={},
            plugin_root=plugin_dir,
        )

        logger.info(
            "plugin.loaded_cc",
            plugin=name,
            plugin_dir=plugin_dir,
            mcp_count=len(mcp_servers),
        )
        return config

    # ------------------------------------------------------------------
    # 纯 Skills 集合加载
    # ------------------------------------------------------------------

    def _load_skills_collection(self, plugin_dir: str) -> "PluginConfig":
        """将纯 skills/ 目录包装为 PluginConfig（无 hooks、无 MCP）。"""
        name = os.path.basename(os.path.abspath(plugin_dir))

        from executor.plugins.plugin_types import PluginConfig

        config = PluginConfig(
            name=name,
            description=f"Skills collection from {plugin_dir}",
            version="1.0.0",
            skills_dir=os.path.join(plugin_dir, "skills"),
            hooks_config={},
            mcp_servers=[],
            agent_overrides={},
            plugin_root=plugin_dir,
        )

        logger.info(
            "plugin.loaded_skills_only",
            plugin=name,
            plugin_dir=plugin_dir,
        )
        return config

    # ------------------------------------------------------------------
    # export_to_cc（ADR-054）
    # ------------------------------------------------------------------

    def export_to_cc(self, config: "PluginConfig") -> ConversionReport:
        """将 Prism PluginConfig 导出为 CC 兼容格式，返回 ConversionReport（ADR-054）。

        转换规则（双向不对称，PRD 明确允许 Prism→CC 可能不完整）：
          - name / description / version → cc_plugin_json 直接映射
          - skills_dir 存在 → cc_plugin_json.skills_path 标记（zip 中保留目录结构注释）
          - hooks_config 存在 → cc_plugin_json.hooks_path 标记
          - mcp_servers → cc_plugin_json.mcp_servers（name 冲突时写 warnings）
          - agent_overrides.vertical_tuning → lost_fields（CC 不支持）
          - agent_overrides.harness_overrides → lost_fields（CC 不支持）

        返回值（ConversionReport）：
          - success:         True（即使有 lost_fields，只要 zip 构建成功）
          - cc_compat_zip:   包含 plugin.json + README 的 zip 字节
          - lost_fields:     Prism 扩展字段清单
          - warnings:        MCP 名称冲突等告警
          - plugin_name:     config.name
          - cc_plugin_json:  生成的 plugin.json dict
        """
        lost_fields: list[str] = []
        warnings_list: list[str] = []

        # --- 构建 cc_plugin_json ---
        cc_json: dict = {
            "name": config.name,
            "description": config.description,
            "version": config.version,
        }

        # skills_dir
        if config.skills_dir:
            cc_json["skills"] = "./skills"

        # hooks_config
        if config.hooks_config:
            cc_json["hooks"] = "./hooks"

        # MCP servers（CC 用 "mcp-servers" key）
        seen_mcp_names: set[str] = set()
        if config.mcp_servers:
            mcp_list: list[dict] = []
            for srv in config.mcp_servers:
                srv_name = srv.get("name", "unknown")
                if srv_name in seen_mcp_names:
                    warnings_list.append(
                        f"MCP server name conflict: '{srv_name}' appears multiple times"
                    )
                else:
                    seen_mcp_names.add(srv_name)
                mcp_list.append(
                    {
                        "name": srv_name,
                        "command": srv.get("command", ""),
                        "args": srv.get("args", []),
                        "env": srv.get("env", {}),
                    }
                )
            cc_json["mcp-servers"] = mcp_list

        # --- lost_fields：Prism 扩展字段（CC 不支持）---
        if isinstance(config.agent_overrides, dict):
            if "vertical_tuning" in config.agent_overrides:
                lost_fields.append("prism.vertical_tuning")
            if "harness_overrides" in config.agent_overrides:
                lost_fields.append("prism.harness_overrides")
            # 其余 agent_overrides 键
            for key in config.agent_overrides:
                if key not in ("vertical_tuning", "harness_overrides"):
                    lost_fields.append(f"prism.agent_overrides.{key}")

        # PluginScope 不映射到 CC
        scope_val = config.scope.value if hasattr(config.scope, "value") else str(config.scope)
        if scope_val not in ("", "user"):
            lost_fields.append(f"prism.scope={scope_val}")

        # user_config 不映射到 CC
        if getattr(config, "user_config", None):
            lost_fields.append("prism.user_config")

        # --- 构建 zip ---
        zip_bytes = self._build_cc_zip(config, cc_json, warnings_list)

        logger.info(
            "plugin.exported_to_cc",
            plugin=config.name,
            lost_fields=lost_fields,
            warnings=warnings_list,
            zip_size=len(zip_bytes),
        )

        return ConversionReport(
            success=True,
            cc_compat_zip=zip_bytes,
            lost_fields=lost_fields,
            warnings=warnings_list,
            plugin_name=config.name,
            cc_plugin_json=cc_json,
        )

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    @staticmethod
    def _read_yaml(yaml_path: str) -> dict:
        """读取并解析 YAML 文件（使用标准库 PyYAML；若不可用则 fallback JSON）。"""
        with open(yaml_path, encoding="utf-8") as fh:
            content = fh.read()
        try:
            import yaml  # type: ignore[import-untyped]

            result = yaml.safe_load(content)
        except ImportError:
            # fallback：尝试 JSON（plugin.yaml 有时是合法 JSON）
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                raise PluginSchemaError(
                    f"无法解析 {yaml_path}：PyYAML 不可用且内容不是合法 JSON",
                    errors=[{"loc": ["<file>"], "msg": "parse error", "type": "parse_error"}],
                )
        return result if isinstance(result, dict) else {}

    @staticmethod
    def _validate_plugin_yaml(raw: dict, yaml_path: str) -> PluginYamlSchema:
        """Pydantic 严格校验 plugin.yaml（ADR-055）。

        缺必填字段（name）→ PluginSchemaError（HTTP 422）。
        """
        if not _PYDANTIC_AVAILABLE:
            # fallback：手动检查 name
            if not raw.get("name"):
                raise PluginSchemaError(
                    f"{yaml_path}: 缺少必填字段 'name'",
                    errors=[{"loc": ["name"], "msg": "field required", "type": "missing"}],
                )
            return PluginYamlSchema(**raw)  # type: ignore[call-arg]

        try:
            return PluginYamlSchema(**raw)  # type: ignore[call-arg]
        except _ValidationError as exc:  # type: ignore[misc]
            errors = exc.errors()  # type: ignore[attr-defined]
            raise PluginSchemaError(
                f"{yaml_path}: plugin.yaml schema 校验失败 — {len(errors)} 个字段错误",
                errors=errors,
            ) from exc

    @staticmethod
    def _scan_hooks_dir(hooks_dir: str) -> dict:
        """扫描 hooks/ 目录，返回 hooks_config 骨架（Phase 1 handler 列表为空）。

        按约定文件名推断 event_type：
          preToolUse.*   → "pre_tool_use"
          postToolUse.*  → "post_tool_use"
          preUserTurn.*  → "pre_user_turn"
          postUserTurn.* → "post_user_turn"
        其他文件：使用文件名（无扩展名）作为 event_type。
        """
        hooks_config: dict = {}
        try:
            for fname in os.listdir(hooks_dir):
                if fname.startswith("."):
                    continue
                stem = os.path.splitext(fname)[0]
                # CC 命名约定 → Prism event_type 映射
                event_map = {
                    "preToolUse": "pre_tool_use",
                    "postToolUse": "post_tool_use",
                    "preUserTurn": "pre_user_turn",
                    "postUserTurn": "post_user_turn",
                }
                event_type = event_map.get(stem, stem)
                handler_path = os.path.join(hooks_dir, fname)
                handler_type = "command" if fname.endswith((".sh", ".bat")) else "command"
                hooks_config[event_type] = [
                    {
                        "type": handler_type,
                        "command": handler_path,
                        "matcher": "",
                    }
                ]
        except OSError:
            pass
        return hooks_config

    @staticmethod
    def _scan_mcp_servers_dir(mcp_dir: str) -> list[dict]:
        """扫描 mcp-servers/ 或 mcp/ 目录，返回 mcp_servers 列表骨架。

        Phase 1：读取 config.json（若存在）；否则仅记录子目录名为 stub。
        """
        mcp_servers: list[dict] = []
        try:
            config_json = os.path.join(mcp_dir, "config.json")
            if os.path.isfile(config_json):
                with open(config_json, encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, list):
                    mcp_servers = data
                elif isinstance(data, dict):
                    # CC 格式可能是 {name: {command, args, env}} 的 dict
                    for srv_name, srv_cfg in data.items():
                        entry = {"name": srv_name}
                        if isinstance(srv_cfg, dict):
                            entry.update(srv_cfg)
                        mcp_servers.append(entry)
            else:
                # 无 config.json：每个子目录作为 stub
                for entry in os.listdir(mcp_dir):
                    if os.path.isdir(os.path.join(mcp_dir, entry)):
                        mcp_servers.append({"name": entry, "command": "", "args": [], "env": {}})
        except OSError:
            pass
        return mcp_servers

    @staticmethod
    def _build_cc_zip(
        config: "PluginConfig",
        cc_json: dict,
        warnings_list: list[str],
    ) -> bytes:
        """构建 CC 兼容 zip 字节流。

        zip 内容：
          plugin.json          — cc_json 序列化
          README.md            — 从 plugin_root 复制（若存在），否则生成占位
          CONVERSION_NOTES.md  — lost_fields + warnings 说明（供调用方审查）
        """
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            # plugin.json
            zf.writestr(
                "plugin.json",
                json.dumps(cc_json, ensure_ascii=False, indent=2),
            )

            # README.md（从 plugin_root 复制或生成占位）
            readme_src = os.path.join(config.plugin_root, "README.md") if config.plugin_root else ""
            if readme_src and os.path.isfile(readme_src):
                zf.write(readme_src, "README.md")
            else:
                zf.writestr(
                    "README.md",
                    f"# {config.name}\n\n{config.description}\n",
                )

            # CONVERSION_NOTES.md — 详尽报告（禁止静默成功）
            notes_lines = [
                f"# Prism → CC Conversion Notes",
                f"",
                f"Plugin: {config.name} v{config.version}",
                f"",
            ]
            if warnings_list:
                notes_lines += ["## Warnings", ""] + [f"- {w}" for w in warnings_list] + [""]
            if config.plugin_root:
                notes_lines += [f"## Lost Fields (Prism-only, not supported by CC)", ""]
                if warnings_list or True:  # always write section
                    lost = []
                    if isinstance(config.agent_overrides, dict):
                        if "vertical_tuning" in config.agent_overrides:
                            lost.append("prism.vertical_tuning")
                        if "harness_overrides" in config.agent_overrides:
                            lost.append("prism.harness_overrides")
                    if lost:
                        notes_lines += [f"- {f}" for f in lost]
                    else:
                        notes_lines.append("(none)")
                    notes_lines.append("")
            notes_lines += [
                "## Directory Structure",
                "",
                "```",
                f"{config.name}/",
                "  plugin.json",
            ]
            if cc_json.get("skills"):
                notes_lines.append("  skills/   (Skills 目录，格式与 Prism 完全一致)")
            if cc_json.get("hooks"):
                notes_lines.append("  hooks/    (Hooks 目录，handler 协议一致)")
            if cc_json.get("mcp-servers"):
                notes_lines.append("  mcp-servers/  (MCP 配置，目录名 CC 约定)")
            notes_lines += ["```", ""]

            zf.writestr("CONVERSION_NOTES.md", "\n".join(notes_lines))

        return buf.getvalue()
