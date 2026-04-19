"""
ResourceMonitor — 资源监控（百分比阈值）ADR-111

v4 核心修订：按百分比阈值而非绝对值（70% warn / 85% critical），
兼容升级到 4C4G 或降级到 1C1G。

额外监控：CPU % / 子进程数 / 队列深度。

采样策略：
  - Backend 进程内存使用百分比 = RSS / total_mem * 100
  - 系统内存百分比 = psutil.virtual_memory().percent
  - CPU 百分比 = psutil.cpu_percent(interval=None)（非阻塞）
  - 子进程数 = len(psutil.Process(pid).children(recursive=True))

告警策略（ADR-111）：
  - warn:     内存 > 70% 或 CPU > 80%
  - critical: 内存 > 85% 或 CPU > 95%
  - ok:       均未触发

队列深度由调用方注入（避免循环导入 task_service）。
"""

from __future__ import annotations

import logging
import os
from typing import Any

import psutil

import structlog
logger = structlog.get_logger()

# ============================================================
# ADR-111 百分比阈值常量
# ============================================================

MEMORY_WARN_PCT: float = 70.0      # 内存使用率 warn 阈值（%）
MEMORY_CRITICAL_PCT: float = 85.0  # 内存使用率 critical 阈值（%）
CPU_WARN_PCT: float = 80.0         # CPU 使用率 warn 阈值（%）
CPU_CRITICAL_PCT: float = 95.0     # CPU 使用率 critical 阈值（%）


class ResourceMonitor:
    """资源监控器（ADR-111 百分比阈值）。

    所有阈值均为百分比，与宿主机绝对内存量无关，
    兼容 2C2G / 4C4G / 1C1G 等不同资源配置。
    """

    def __init__(
        self,
        memory_warn_pct: float = MEMORY_WARN_PCT,
        memory_critical_pct: float = MEMORY_CRITICAL_PCT,
        cpu_warn_pct: float = CPU_WARN_PCT,
        cpu_critical_pct: float = CPU_CRITICAL_PCT,
    ) -> None:
        self._mem_warn = memory_warn_pct
        self._mem_critical = memory_critical_pct
        self._cpu_warn = cpu_warn_pct
        self._cpu_critical = cpu_critical_pct
        self._pid = os.getpid()

    # ----------------------------------------------------------
    # 采样方法
    # ----------------------------------------------------------

    def get_memory_percent(self) -> float:
        """系统整体内存使用百分比（psutil.virtual_memory().percent）。

        ADR-111: 使用系统百分比而非 Backend 进程绝对 RSS，
        确保阈值与宿主机内存规格无关。
        """
        return psutil.virtual_memory().percent

    def get_backend_memory_mb(self) -> float:
        """Backend 进程 RSS（MB），用于调试辅助。"""
        try:
            return psutil.Process(self._pid).memory_info().rss / (1024 * 1024)
        except psutil.NoSuchProcess:
            return 0.0

    def get_cpu_percent(self) -> float:
        """系统 CPU 使用百分比（非阻塞，返回上次采样间隔平均值）。

        首次调用会返回 0.0（psutil 特性），因此建议进程启动后预热一次。
        """
        return psutil.cpu_percent(interval=None)

    def get_child_process_count(self) -> int:
        """Backend 子进程数量（Agent 执行器等）。"""
        try:
            parent = psutil.Process(self._pid)
            return len(parent.children(recursive=True))
        except psutil.NoSuchProcess:
            return 0

    def get_child_processes(self) -> list[dict]:
        """获取 Backend 子进程详细信息列表。"""
        try:
            parent = psutil.Process(self._pid)
            children = parent.children(recursive=True)
        except psutil.NoSuchProcess:
            return []

        result = []
        for c in children:
            try:
                result.append(
                    {
                        "pid": c.pid,
                        "name": c.name(),
                        "memory_mb": round(
                            c.memory_info().rss / (1024 * 1024), 1
                        ),
                        "cpu_percent": c.cpu_percent(interval=None),
                        "status": c.status(),
                    }
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return result

    def get_system_memory_info(self) -> dict:
        """系统内存详情（供 /health/detailed 端点使用）。"""
        mem = psutil.virtual_memory()
        return {
            "total_mb": round(mem.total / (1024 * 1024), 1),
            "used_mb": round(mem.used / (1024 * 1024), 1),
            "available_mb": round(mem.available / (1024 * 1024), 1),
            "percent": mem.percent,
        }

    # ----------------------------------------------------------
    # 综合健康检查（ADR-111 百分比驱动）
    # ----------------------------------------------------------

    def check_health(self, queue_depth: int = 0) -> dict:
        """综合健康检查（ADR-111）。

        Returns::

            {
                "status": "ok" | "warning" | "critical",
                "memory_percent": 62.3,          # 系统内存使用率（%）
                "cpu_percent": 15.0,             # CPU 使用率（%）
                "backend_memory_mb": 210.5,      # Backend 进程 RSS（MB，调试用）
                "child_count": 2,                # 子进程数
                "queue_depth": 0,                # 任务队列深度（调用方注入）
                "system_memory": {...},          # 内存详情
                "warnings": ["..."],             # 告警消息列表
                "thresholds": {                  # 当前阈值（便于前端展示）
                    "memory_warn_pct": 70.0,
                    "memory_critical_pct": 85.0,
                    "cpu_warn_pct": 80.0,
                    "cpu_critical_pct": 95.0,
                },
            }

        告警逻辑（ADR-111）：
          critical > warning > ok（两者同时满足时取更严重级别）
        """
        mem_pct = self.get_memory_percent()
        cpu_pct = self.get_cpu_percent()
        backend_mb = self.get_backend_memory_mb()
        child_count = self.get_child_process_count()
        sys_mem = self.get_system_memory_info()

        warnings: list[str] = []
        status = "ok"

        # 内存百分比检查（ADR-111）
        if mem_pct >= self._mem_critical:
            warnings.append(
                f"Memory critical: {mem_pct:.1f}% >= {self._mem_critical}%"
            )
            status = "critical"
        elif mem_pct >= self._mem_warn:
            warnings.append(
                f"Memory warning: {mem_pct:.1f}% >= {self._mem_warn}%"
            )
            if status == "ok":
                status = "warning"

        # CPU 百分比检查（ADR-111）
        if cpu_pct >= self._cpu_critical:
            warnings.append(
                f"CPU critical: {cpu_pct:.1f}% >= {self._cpu_critical}%"
            )
            status = "critical"
        elif cpu_pct >= self._cpu_warn:
            warnings.append(
                f"CPU warning: {cpu_pct:.1f}% >= {self._cpu_warn}%"
            )
            if status == "ok":
                status = "warning"

        return {
            "status": status,
            "memory_percent": round(mem_pct, 1),
            "cpu_percent": round(cpu_pct, 1),
            "backend_memory_mb": round(backend_mb, 1),
            "child_count": child_count,
            "queue_depth": queue_depth,
            "system_memory": sys_mem,
            "warnings": warnings,
            "thresholds": {
                "memory_warn_pct": self._mem_warn,
                "memory_critical_pct": self._mem_critical,
                "cpu_warn_pct": self._cpu_warn,
                "cpu_critical_pct": self._cpu_critical,
            },
        }

    def is_memory_warn(self) -> bool:
        """内存使用率是否超过 warn 阈值（70%）。"""
        return self.get_memory_percent() >= self._mem_warn

    def is_memory_critical(self) -> bool:
        """内存使用率是否超过 critical 阈值（85%）。"""
        return self.get_memory_percent() >= self._mem_critical

    # ----------------------------------------------------------
    # AlertDispatcher 接入（ADR-120 PRD Part B §6）
    # ----------------------------------------------------------

    async def check_and_dispatch(
        self,
        alert_dispatcher: "Any | None" = None,
        queue_depth: int = 0,
    ) -> dict:
        """
        资源检查 + AlertDispatcher 告警路由（ADR-120）。

        - 内存 >= 85%（critical）  → dispatch("critical", "resource.memory", ...)
        - 内存 >= 70%（warning）   → dispatch("warning", "resource.memory", ...)
        - 同样规则适用于 CPU（resource.cpu）

        ADR-120 PRD Part B §6：
          ResourceMonitor 调用 AlertDispatcher.dispatch("warning" when 70%+/"critical" when 85%+,
          "resource.memory", detail)

        Returns:
            check_health() 的结果 dict
        """
        health = self.check_health(queue_depth=queue_depth)
        status = health["status"]

        if alert_dispatcher is None or status == "ok":
            return health

        mem_pct = health["memory_percent"]
        cpu_pct = health["cpu_percent"]

        # 内存告警
        if mem_pct >= self._mem_critical:
            try:
                await alert_dispatcher.dispatch(
                    severity="critical",
                    event_type="resource.memory",
                    detail={
                        "memory_percent": mem_pct,
                        "threshold_critical": self._mem_critical,
                        "backend_memory_mb": health.get("backend_memory_mb", 0.0),
                        "child_count": health.get("child_count", 0),
                        "queue_depth": queue_depth,
                    },
                    resource_type="system",
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "resource_monitor.alert_dispatcher_failed",
                    event="resource.memory.critical",
                    error=str(exc),
                )
        elif mem_pct >= self._mem_warn:
            try:
                await alert_dispatcher.dispatch(
                    severity="warning",
                    event_type="resource.memory",
                    detail={
                        "memory_percent": mem_pct,
                        "threshold_warn": self._mem_warn,
                        "backend_memory_mb": health.get("backend_memory_mb", 0.0),
                        "child_count": health.get("child_count", 0),
                        "queue_depth": queue_depth,
                    },
                    resource_type="system",
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "resource_monitor.alert_dispatcher_failed",
                    event="resource.memory.warning",
                    error=str(exc),
                )

        # CPU 告警
        if cpu_pct >= self._cpu_critical:
            try:
                await alert_dispatcher.dispatch(
                    severity="critical",
                    event_type="resource.cpu",
                    detail={
                        "cpu_percent": cpu_pct,
                        "threshold_critical": self._cpu_critical,
                    },
                    resource_type="system",
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "resource_monitor.alert_dispatcher_failed",
                    event="resource.cpu.critical",
                    error=str(exc),
                )
        elif cpu_pct >= self._cpu_warn:
            try:
                await alert_dispatcher.dispatch(
                    severity="warning",
                    event_type="resource.cpu",
                    detail={
                        "cpu_percent": cpu_pct,
                        "threshold_warn": self._cpu_warn,
                    },
                    resource_type="system",
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "resource_monitor.alert_dispatcher_failed",
                    event="resource.cpu.warning",
                    error=str(exc),
                )

        return health
