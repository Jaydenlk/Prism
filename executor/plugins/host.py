"""
PluginHost — 统一管理 Skill + Hook + MCP

DOC-05 Task 5.4: PluginHost 统一管理与垂类特调（ADR-050）

职责：
1. 加载 Plugin（解析 plugin.yaml → 变量替换 → 注册 Skill + Hook + MCP）
2. 卸载 Plugin（注销所有资源）
3. 向 PromptAssembler 提供动态上下文（Skill 描述 + MCP instructions）
4. 向 QueryEngine 提供 Agent 行为覆盖（垂类特调）

生命周期：
- Agent 执行器启动时，PluginHost 根据 Session config 加载 Plugin
- Session 结束时，PluginHost.shutdown() 卸载所有 Plugin，清理 MCP 子进程
  （解 Task 5.2 留的 TODO：MCPClient.stop() 统一由此 finally 块调用）

变量替换系统（ADR-050）：
支持以下变量（在 plugin.yaml 字符串字段中使用 ${VAR} 语法）：
  ${PRISM_PLUGIN_ROOT}   — Plugin 根目录绝对路径
  ${PRISM_PLUGIN_DATA}   — Plugin 数据目录（<data_root>/plugins/<name>）
  ${PRISM_SKILL_DIR}     — Plugin 内 skills/ 子目录路径
  ${PRISM_SESSION_ID}    — 当前 Session ID（运行时上下文）
  ${PRISM_USER_ID}       — 当前 User ID（运行时上下文）
  ${user_config.X}       — 用户安装时填写的自定义配置项 X
  ${CLAUDE_PLUGIN_ROOT}  — CC 兼容映射，等价于 ${PRISM_PLUGIN_ROOT}
  ${env.X}               — 环境变量 X（白名单过滤，避免变量污染）

变量替换白名单安全约束（sandbox）：
  - ${env.X} 只允许访问 ENV_WHITELIST 中明确列出的环境变量
  - ${secret.X} 留桩（跨进程场景需走 security.decrypt_value，Phase 2 实现）
  - 未知变量（非白名单 env、非定义变量）保持原样不替换（而非引发异常）

加载顺序（ADR-050）：
  Platform（平台内置）→ User（用户安装）→ Session（会话临时）
  冲突时高优先级覆盖低优先级，检测到冲突写 structlog audit 事件。

进程边界：本模块只 import executor.*，禁止 import backend.app.*
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

import structlog

from executor.plugins.mcp_client import MCPClient, MCPToolWrapper
from executor.plugins.namespace import PluginNamespace
from executor.plugins.plugin_types import PluginConfig, PluginScope

if TYPE_CHECKING:
    from executor.engine.prompt_assembler import PromptAssembler
    from executor.harness.hooks.handlers import HookHandlerConfig
    from executor.harness.hooks.system import HookSystem
    from executor.plugins.cc_compat import CCPluginAdapter
    from executor.plugins.skill_loader import SkillLoader
    from executor.tools.registry import ToolRegistry

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# 变量替换系统 — 白名单安全约束（sandbox）
# ---------------------------------------------------------------------------

# ${env.X} 允许访问的环境变量白名单
ENV_WHITELIST: frozenset[str] = frozenset(
    {
        "HOME",
        "PATH",
        "TMPDIR",
        "TMP",
        "TEMP",
        "USER",
        "LANG",
        "LC_ALL",
        "PRISM_DATA_ROOT",   # Prism 平台配置可注入
        "PRISM_PLUGIN_DIR",  # Prism 插件根目录环境变量
    }
)

# 默认 Plugin 数据根目录（可通过 env PRISM_DATA_ROOT 覆盖）
_DEFAULT_DATA_ROOT = "/app/data"


class PluginVariableExpander:
    """变量替换引擎（ADR-050）

    安全约束（sandbox）：
    - ${env.X} 只允许访问 ENV_WHITELIST 中的环境变量，未在白名单内的保持原样
    - ${secret.X} 目前留桩（返回原始字符串），Phase 2 走 security.decrypt_value
    - 未知变量保持原样（不抛异常），避免 plugin.yaml 中的未知占位符炸毁加载流程
    """

    def __init__(
        self,
        plugin_config: PluginConfig,
        session_id: str = "",
        user_id: str = "",
    ) -> None:
        self._config = plugin_config
        self._session_id = session_id
        self._user_id = user_id
        self._data_root = os.environ.get("PRISM_DATA_ROOT", _DEFAULT_DATA_ROOT)

    def expand(self, text: str) -> str:
        """在字符串 text 中展开所有 ${VAR} 变量占位符。

        1. CC 兼容：先将 ${CLAUDE_PLUGIN_ROOT} → ${PRISM_PLUGIN_ROOT}
        2. 依次替换已定义变量
        3. ${env.X}：白名单检查后替换
        4. ${secret.X}：Phase 1 留桩（原样保留）
        5. ${user_config.X}：查 plugin_config.user_config
        6. 未知变量：保持原样
        """
        if not text or "${" not in text:
            return text

        # CC 兼容映射（最先处理）
        text = text.replace("${CLAUDE_PLUGIN_ROOT}", "${PRISM_PLUGIN_ROOT}")

        # 构建内置变量表
        plugin_root = self._config.plugin_root or ""
        skill_dir = (
            os.path.join(plugin_root, self._config.skills_dir)
            if self._config.skills_dir and plugin_root
            else (self._config.skills_dir or "")
        )
        builtin: dict[str, str] = {
            "PRISM_PLUGIN_ROOT": plugin_root,
            "PRISM_PLUGIN_DATA": os.path.join(
                self._data_root, "plugins", self._config.name
            ),
            "PRISM_SKILL_DIR": skill_dir,
            "PRISM_SESSION_ID": self._session_id,
            "PRISM_USER_ID": self._user_id,
        }

        def _replace(match: re.Match) -> str:
            var = match.group(1)  # 去掉 ${ 和 }

            # 内置变量
            if var in builtin:
                return builtin[var]

            # ${env.X}：白名单过滤
            if var.startswith("env."):
                env_key = var[4:]
                if env_key in ENV_WHITELIST:
                    return os.environ.get(env_key, match.group(0))
                # 未在白名单内：保持原样（sandbox 约束）
                logger.debug(
                    "plugin.var.env_not_whitelisted",
                    plugin=self._config.name,
                    env_key=env_key,
                )
                return match.group(0)

            # ${secret.X}：Phase 1 留桩（跨进程需走 security.decrypt_value）
            if var.startswith("secret."):
                logger.debug(
                    "plugin.var.secret_stub",
                    plugin=self._config.name,
                    var=var,
                )
                return match.group(0)  # 原样保留

            # ${user_config.X}
            if var.startswith("user_config."):
                key = var[len("user_config."):]
                return str(self._config.user_config.get(key, match.group(0)))

            # 未知变量：保持原样（不抛异常）
            return match.group(0)

        return re.sub(r"\$\{([^}]+)\}", _replace, text)

    def expand_dict(self, data: dict) -> dict:
        """递归展开 dict 中所有字符串值的变量占位符。

        只处理 str 类型的值；list/dict 类型递归处理；其他类型原样返回。
        """
        result: dict = {}
        for k, v in data.items():
            if isinstance(v, str):
                result[k] = self.expand(v)
            elif isinstance(v, dict):
                result[k] = self.expand_dict(v)
            elif isinstance(v, list):
                result[k] = self.expand_list(v)
            else:
                result[k] = v
        return result

    def expand_list(self, data: list) -> list:
        """递归展开 list 中所有字符串元素的变量占位符。"""
        result = []
        for item in data:
            if isinstance(item, str):
                result.append(self.expand(item))
            elif isinstance(item, dict):
                result.append(self.expand_dict(item))
            elif isinstance(item, list):
                result.append(self.expand_list(item))
            else:
                result.append(item)
        return result


# ---------------------------------------------------------------------------
# PluginHost — 统一管理入口
# ---------------------------------------------------------------------------


class PluginHost:
    """统一管理 Skill + Hook + MCP（ADR-050 PluginHost 生命周期）

    使用方式（单次 Session）：
        host = PluginHost(skill_loader, hook_system, tool_registry, assembler)
        await host.load_plugin(config, session_id=..., user_id=...)
        # ... session 运行 ...
        await host.shutdown()   # 卸载所有 Plugin，清理 MCP 子进程

    Task 5.2 TODO 解决：
        MCPClient.stop() 统一由 host.shutdown() 的 finally 块调用，
        无论 session 正常/异常结束都保证清理（见 shutdown() 实现）。
    """

    def __init__(
        self,
        skill_loader: "SkillLoader",
        hook_system: "HookSystem",
        tool_registry: "ToolRegistry",
        assembler: "PromptAssembler",
        cc_adapter: "CCPluginAdapter | None" = None,
    ) -> None:
        self._skill_loader = skill_loader
        self._hook_system = hook_system
        self._registry = tool_registry
        self._assembler = assembler

        # Task 5.7: CC 兼容层适配器（ADR-054/ADR-055）
        if cc_adapter is None:
            from executor.plugins.cc_compat import CCPluginAdapter as _CCAdapter
            cc_adapter = _CCAdapter()
        self._cc_adapter: "CCPluginAdapter" = cc_adapter

        # plugin_name → PluginConfig（已加载 Plugin 的注册表）
        self._loaded_plugins: dict[str, PluginConfig] = {}

        # 所有已启动的 MCPClient 列表（跨 Plugin 统一管理，shutdown 统一停止）
        self._mcp_clients: list["MCPClient"] = []

        # server_name → instructions（用于 PromptAssembler 动态 section）
        self._mcp_instructions: dict[str, str] = {}

    # ------------------------------------------------------------------
    # 加载 Plugin
    # ------------------------------------------------------------------

    async def load_plugin(
        self,
        config: PluginConfig,
        *,
        session_id: str = "",
        user_id: str = "",
    ) -> None:
        """加载 Plugin：变量替换 → 冲突检测 → 注册 Skill + Hook + MCP。

        步骤：
        1. 变量替换（PluginVariableExpander 展开 plugin.yaml 所有字符串字段）
        2. 冲突检测（同名 Plugin 已加载时，高优先级 scope 覆盖低优先级，写 audit）
        3. 使用 PluginNamespace 隔离资源命名
        4. Level 0 注册 Plugin 内的 Skills（若 skills_dir 非空）
        5. 注册 Plugin 的 Hooks（带命名空间 hook_id）
        6. 启动 Plugin 的 MCP Servers，注册工具，使 PromptAssembler cache 失效
        7. 写入 _loaded_plugins
        """
        # --- Step 1: 变量替换 ---
        expander = PluginVariableExpander(config, session_id=session_id, user_id=user_id)
        config = self._apply_variable_expansion(config, expander)

        # --- Step 2: 冲突检测（ADR-050 三级加载顺序） ---
        if config.name in self._loaded_plugins:
            existing = self._loaded_plugins[config.name]
            if existing.scope.priority >= config.scope.priority:
                logger.info(
                    "plugin.load.skipped_lower_priority",
                    plugin=config.name,
                    existing_scope=existing.scope.value,
                    incoming_scope=config.scope.value,
                    audit=True,
                )
                return
            # 新 scope 优先级更高 → 先卸载旧的，再加载新的
            logger.warning(
                "plugin.load.conflict_override",
                plugin=config.name,
                old_scope=existing.scope.value,
                new_scope=config.scope.value,
                audit=True,
            )
            await self.unload_plugin(config.name)

        ns = PluginNamespace(config.name)

        # --- Step 3: Skill Level 0 注册 ---
        if config.skills_dir:
            old_dir = self._skill_loader._skills_dir
            self._skill_loader._skills_dir = config.skills_dir
            self._skill_loader.scan_and_register()
            self._skill_loader._skills_dir = old_dir

        # --- Step 4: Hook 注册（带命名空间 hook_id） ---
        for event_type, handler_list in config.hooks_config.items():
            for i, raw_config in enumerate(handler_list):
                if isinstance(raw_config, dict):
                    # 延迟 import 避免循环依赖
                    from executor.harness.hooks.handlers import HookHandlerConfig

                    hc = HookHandlerConfig(
                        type=raw_config.get("type", "command"),  # type: ignore[arg-type]
                        command=raw_config.get("command", ""),
                        url=raw_config.get("url", ""),
                        prompt_template=raw_config.get("prompt_template", ""),
                        prompt_model=raw_config.get("prompt_model", ""),
                        agent_type=raw_config.get("agent_type", ""),
                        matcher=raw_config.get("matcher", ""),
                    )
                    hook_id = f"plugin:{config.name}:{event_type}:{i}"
                    self._hook_system.register(
                        event_type, hc, hook_id=hook_id, priority=50
                    )

        # --- Step 5: MCP Servers ---
        for mcp_conf in config.mcp_servers:
            qualified_server = ns.qualify(mcp_conf.get("name", "unknown"))
            await self._start_mcp_server({**mcp_conf, "name": qualified_server})

        # PluginHost.update_tools — 使 PromptAssembler cache 失效
        self._assembler.update_tools(self._registry.list_definitions())

        self._loaded_plugins[config.name] = config
        logger.info(
            "plugin.loaded",
            plugin=config.name,
            scope=config.scope.value,
            skills_dir=config.skills_dir,
            mcp_count=len(config.mcp_servers),
            hook_events=list(config.hooks_config.keys()),
        )

    # ------------------------------------------------------------------
    # 从目录加载（Task 5.7 — CC 兼容层入口）
    # ------------------------------------------------------------------

    async def load_plugin_from_dir(
        self,
        plugin_dir: str,
        *,
        session_id: str = "",
        user_id: str = "",
    ) -> PluginConfig:
        """从目录自动检测格式（CC / Prism / skills_only）并加载 Plugin。

        ADR-054/ADR-055 集成点：
          - 调用 CCPluginAdapter.load(plugin_dir) 统一检测格式并转换为 PluginConfig
          - 若 plugin.yaml 缺必填字段，CCPluginAdapter 抛 PluginSchemaError（Backend 转 422）
          - 若格式无法识别，抛 PluginFormatError

        返回值：已加载的 PluginConfig（供调用方查看转换结果）。
        """
        config = self._cc_adapter.load(plugin_dir)
        await self.load_plugin(config, session_id=session_id, user_id=user_id)
        return config

    # ------------------------------------------------------------------
    # 卸载 Plugin
    # ------------------------------------------------------------------

    async def unload_plugin(self, plugin_name: str) -> None:
        """卸载指定 Plugin：注销 Hooks，清理标记（MCP 由 shutdown() 统一停止）。

        Phase 1 简化：MCP Client 不按 Plugin 追踪归属，shutdown() 统一停止。
        Phase 2 可按 Plugin 追踪每个 MCPClient，精确卸载。
        """
        if plugin_name not in self._loaded_plugins:
            return

        # 注销 Plugin 的所有 scoped Hooks
        self._hook_system.unregister_by_prefix(f"plugin:{plugin_name}:")

        # 注销 Plugin Skills 的 scoped Hooks（若 Skill 未卸载，则一并清除）
        self._hook_system.unregister_by_prefix(f"skill:")

        self._loaded_plugins.pop(plugin_name, None)

        # cache 失效
        self._assembler.update_tools(self._registry.list_definitions())

        logger.info("plugin.unloaded", plugin=plugin_name)

    async def unload_all(self) -> None:
        """卸载所有已加载 Plugin（不停止 MCP，由 shutdown() 统一处理）。"""
        for name in list(self._loaded_plugins.keys()):
            await self.unload_plugin(name)

    async def shutdown(self) -> None:
        """Session 结束时调用：卸载所有 Plugin + 停止所有 MCP 子进程。

        解 Task 5.2 留的 TODO：MCPClient.stop() 由此 finally 块统一调用，
        保证无论 Session 正常结束还是异常退出，MCP 子进程都被清理。

        调用方（HarnessRuntime.on_session_end 或 __main__.py finally 块）应 await 此方法。
        """
        # 先卸载所有 Plugin（注销 Hooks / Skill 钩子）
        await self.unload_all()

        # 停止所有 MCPClient 子进程
        for client in list(self._mcp_clients):
            try:
                await client.stop()
            except Exception as exc:
                logger.warning(
                    "plugin_host.mcp_stop_error",
                    server=getattr(client, "server_name", "?"),
                    error=str(exc),
                )
        self._mcp_clients.clear()
        self._mcp_instructions.clear()
        logger.info("plugin_host.shutdown_complete")

    # ------------------------------------------------------------------
    # 对外查询接口（供 PromptAssembler / QueryEngine）
    # ------------------------------------------------------------------

    def get_skill_descriptions(self, agent_type: str | None = None) -> str:
        """返回所有 Skill 描述（供 PromptAssembler 动态 section）。

        委托给 SkillLoader.get_descriptions_for_prompt()，
        若 agent_type 指定则按 ADR-044 agents 字段过滤。
        """
        return self._skill_loader.get_descriptions_for_prompt(agent_type=agent_type)

    def get_mcp_instructions(self) -> dict[str, str]:
        """返回所有 MCP instructions（供 PromptAssembler <mcp_instructions> section）。

        key = 已命名空间化的 server_name，value = server.info.instructions。
        """
        return dict(self._mcp_instructions)

    def get_agent_overrides(self) -> dict:
        """返回所有 Plugin 的 Agent 行为覆盖（合并）。

        垂类特调场景：Plugin 可以追加或覆盖 Agent 的行为约束（如 max_turns、模型参数约束等）。
        加载顺序保证了 Session scope Plugin 的 overrides 会覆盖 User/Platform scope Plugin。
        """
        merged: dict = {}
        # 按优先级从低到高迭代，高优先级覆盖低优先级
        sorted_configs = sorted(
            self._loaded_plugins.values(),
            key=lambda c: c.scope.priority,
        )
        for config in sorted_configs:
            merged.update(config.agent_overrides)
        return merged

    @property
    def loaded_plugins(self) -> dict[str, PluginConfig]:
        """只读视图：已加载 Plugin 的注册表。"""
        return dict(self._loaded_plugins)

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _apply_variable_expansion(
        self,
        config: PluginConfig,
        expander: PluginVariableExpander,
    ) -> PluginConfig:
        """对 PluginConfig 中所有字符串字段做变量替换，返回新 PluginConfig 实例。

        展开范围：skills_dir、mcp_servers（每项 dict）、hooks_config（递归）。
        name/description/version/scope/agent_overrides 不做展开（语义敏感或非路径字段）。
        """
        return PluginConfig(
            name=config.name,
            description=config.description,
            version=config.version,
            skills_dir=expander.expand(config.skills_dir),
            hooks_config=expander.expand_dict(config.hooks_config),
            mcp_servers=[expander.expand_dict(srv) for srv in config.mcp_servers],
            agent_overrides=config.agent_overrides,
            scope=config.scope,
            plugin_root=expander.expand(config.plugin_root),
            user_config=config.user_config,
        )

    async def start_server(self, server_config: dict) -> None:
        """Public entry: start one MCP server, register its tools, record instructions.

        Use this from external callers (executor bootstrap, etc.).
        Idempotent re-entry is NOT guaranteed; caller must avoid double-starting.
        """
        await self._start_mcp_server(server_config)

    async def _start_mcp_server(self, server_config: dict) -> None:
        """Dispatch on transport: stdio (existing) or http (new).

        Registers tools to ToolRegistry and records instructions after start.
        """
        server_name = server_config["name"]
        transport = server_config.get("transport", "stdio")

        if transport == "http":
            client = MCPClient(
                server_name=server_name,
                transport="http",
                url=server_config["url"],
                headers=server_config.get("headers", {}),
            )
        else:
            command = server_config.get("command", "")
            if not command:
                logger.warning(
                    "plugin_host.mcp_empty_command",
                    server_name=server_name,
                )
                return
            client = MCPClient(
                server_name=server_name,
                transport="stdio",
                command=command,
                args=server_config.get("args", []),
                env=server_config.get("env", {}),
            )

        await client.start()
        self._mcp_clients.append(client)

        tools = await client.list_tools()
        for mcp_tool in tools:
            wrapper = MCPToolWrapper(server_name, mcp_tool, client)
            self._registry.register(wrapper)

        instructions = client.get_instructions()
        if instructions:
            self._mcp_instructions[server_name] = instructions

        logger.info(
            "plugin_host.mcp_started",
            server_name=server_name,
            tool_count=len(tools),
            has_instructions=bool(instructions),
        )
