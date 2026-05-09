"""
Prism v2 — CLI 子进程调度器 (DOC-07 Task 7.4, ADR-066)

职责：
  - 按 ADR-066 标准化启动参数启动 Agent 子进程
  - 并发控制（信号量 MAX_CONCURRENT_RUNS）
  - 超时管理（RUN_TIMEOUT_SECONDS + watchdog）
  - mark_running（subprocess_pid 写入 runs 表）
  - 进程清理

⚠️ 设计约束：
  - 子进程在 Backend 容器内运行（不是独立容器）
  - 启动命令: python -m executor --run-id=... (ADR-066 必传 6 参数)
  - secret 不放 argv，走环境变量 ENCRYPTION_KEY（避免日志泄露）
  - CALLBACK_SECRET 例外：executor 主动 POST 回调时必须带 secret，argv 传递
  - ProcessManager 是单例，由 app lifespan 初始化并挂载到 app.state

ADR-066 subprocess 启动参数规范（来自 DOC-01 v4 §9.1）：
  必传（argv）:
    --run-id=UUID
    --session-id=UUID
    --user-id=UUID
    --callback-url=http://backend:8000/api/v1/internal/callbacks
    --callback-secret=<CALLBACK_SECRET>   # executor 主动回调用
    --redis-url=redis://redis:6379/0
  可选（argv）:
    --resume-from-step=N                  # coordinator 恢复时传
    --otel-trace-id=traceparent-value     # OTel 跨进程传播
  环境变量（不在 argv，避免 ps 日志泄露）:
    ENCRYPTION_KEY                        # Provider decryption
    OTEL_EXPORTER_OTLP_ENDPOINT           # OTLP endpoint（可空）
"""
from __future__ import annotations

import logging
import os
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from app.core.config import Settings

import structlog
logger = structlog.get_logger()


class ProcessManager:
    """
    CLI 子进程调度器 — 单例，由 app lifespan 初始化。

    并发模型：
      - threading.Semaphore 控制最大并发数（MAX_CONCURRENT_RUNS）
      - ThreadPoolExecutor 管理后台线程（等待子进程 + 超时检测）
      - _processes dict 保存 run_id → Popen（用于 kill_run）

    生命周期：
      1. lifespan startup：ProcessManager(settings)
      2. app.state.process_manager = pm
      3. 任务提交：pm.start_run(run_id)
      4. 内部：_run_in_thread 在后台线程管理子进程
      5. lifespan shutdown：pm.shutdown()
    """

    def __init__(self, settings: "Settings") -> None:
        self._settings = settings
        self._semaphore = threading.Semaphore(settings.MAX_CONCURRENT_RUNS)
        self._processes: dict[str, subprocess.Popen] = {}   # run_id → Popen
        self._executor = ThreadPoolExecutor(
            max_workers=settings.MAX_CONCURRENT_RUNS + 4,
            thread_name_prefix="prism-executor",
        )
        self._lock = threading.Lock()
        self._running = True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_run(
        self,
        run_id: str,
        resume_from_step: int | None = None,
    ) -> None:
        """
        异步启动 Agent 子进程。

        如果当前并发已满，后台线程将阻塞等待信号量释放。
        此方法立即返回（non-blocking）。
        """
        if not self._running:
            logger.warning("process_manager.start_run.rejected", run_id=run_id, reason="shutting_down")
            return
        self._executor.submit(self._run_in_thread, run_id, resume_from_step)
        logger.info("process_manager.start_run.submitted", run_id=run_id, resume_from_step=resume_from_step)

    def kill_run(self, run_id: str, force: bool = False) -> bool:
        """
        向指定 run 的子进程发送信号。

        Args:
            run_id:  目标 Run 的 UUID。
            force:   True → SIGKILL；False → SIGTERM（ADR-062）。

        Returns:
            True 表示进程存在且信号已发送；False 表示进程不存在（已退出）。
        """
        with self._lock:
            proc = self._processes.get(run_id)
        if proc is None:
            return False
        try:
            if force:
                proc.kill()     # SIGKILL
            else:
                proc.terminate()  # SIGTERM
            logger.info(
                "process_manager.kill_run",
                run_id=run_id,
                signal="SIGKILL" if force else "SIGTERM",
            )
            return True
        except OSError as exc:
            logger.warning("process_manager.kill_run.failed", run_id=run_id, error=str(exc))
            return False

    def shutdown(self) -> None:
        """
        关闭所有子进程并停止线程池。

        lifespan shutdown 时调用，等待所有后台线程优雅退出（最长 10s）。
        """
        self._running = False
        with self._lock:
            for run_id, proc in list(self._processes.items()):
                try:
                    proc.kill()
                    logger.info("process_manager.shutdown.killed", run_id=run_id)
                except OSError:
                    pass
        self._executor.shutdown(wait=True)
        logger.info("process_manager.shutdown.complete")

    # ------------------------------------------------------------------
    # Internal: subprocess lifecycle
    # ------------------------------------------------------------------

    def _run_in_thread(
        self,
        run_id: str,
        resume_from_step: int | None,
    ) -> None:
        """
        在后台线程中管理子进程完整生命周期：
          1. 获取信号量（并发限制）
          2. 查 DB 获取 Run（session_id / user_id / model 等）
          3. 构造 ADR-066 标准化命令
          4. Popen 启动子进程
          5. 调用 mark_running（写 subprocess_pid 到 runs 表）
          6. proc.wait() 等待完成或超时
          7. 处理超时 / 非正常退出
          8. 释放信号量
        """
        self._semaphore.acquire()
        try:
            self._launch_and_wait(run_id, resume_from_step)
        finally:
            with self._lock:
                self._processes.pop(run_id, None)
            self._semaphore.release()

    def _launch_and_wait(
        self,
        run_id: str,
        resume_from_step: int | None,
    ) -> None:
        """实际启动子进程并等待完成。"""
        from app.core.database import SessionLocal
        from app.models.run import Run

        # 查询 Run（获取 session_id / user_id / otel_trace_id）
        run_row = None
        try:
            with SessionLocal() as db:
                run_row = db.get(Run, run_id)
        except Exception as exc:
            logger.error(
                "process_manager.db_lookup_failed",
                run_id=run_id,
                error=str(exc),
            )
            self._notify_failure(run_id, f"DB lookup failed: {exc}")
            return

        if run_row is None:
            logger.error("process_manager.run_not_found", run_id=run_id)
            self._notify_failure(run_id, "Run not found in database")
            return

        # 构造 ADR-066 标准化命令
        cmd = self._build_command(run_row, resume_from_step=resume_from_step)
        env = self._build_env()

        # 启动子进程
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
        except OSError as exc:
            logger.error(
                "process_manager.popen_failed",
                run_id=run_id,
                error=str(exc),
            )
            self._notify_failure(run_id, f"Failed to start subprocess: {exc}")
            return

        # 注册进程
        with self._lock:
            self._processes[run_id] = proc

        # mark_running（写 subprocess_pid 到 runs 表）
        self._mark_running(run_id, pid=proc.pid)

        logger.info(
            "process_manager.subprocess_started",
            run_id=run_id,
            pid=proc.pid,
            resume_from_step=resume_from_step,
        )

        # 等待完成或超时
        try:
            proc.wait(timeout=self._settings.RUN_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            logger.warning(
                "process_manager.timeout",
                run_id=run_id,
                timeout=self._settings.RUN_TIMEOUT_SECONDS,
            )
            proc.kill()
            proc.wait()
            self._notify_timeout(run_id)
            return

        # 检查退出码
        returncode = proc.returncode
        if returncode not in (0, None):
            stderr_raw = b""
            if proc.stderr:
                try:
                    stderr_raw = proc.stderr.read()
                except OSError:
                    pass
            stderr_text = stderr_raw.decode(errors="replace")[:500]
            logger.error(
                "process_manager.subprocess_failed",
                run_id=run_id,
                returncode=returncode,
                stderr_preview=stderr_text,
            )
            self._notify_failure(
                run_id,
                f"Process exited with code {returncode}: {stderr_text}",
            )
        else:
            # Capture a tail of stderr even on success so subprocess structlog
            # output (which writes to stderr by default) isn't lost — aids
            # observability for middleware / harness events debugging.
            stderr_tail = ""
            if proc.stderr:
                try:
                    stderr_tail = proc.stderr.read().decode(errors="replace")[-4000:]
                except OSError:
                    pass
            logger.info(
                "process_manager.subprocess_done",
                run_id=run_id,
                returncode=returncode,
                stderr_tail=stderr_tail,
            )

    # ------------------------------------------------------------------
    # ADR-066: command + env builders
    # ------------------------------------------------------------------

    def _build_command(
        self,
        run,  # Run ORM instance
        resume_from_step: int | None = None,
    ) -> list[str]:
        """
        ADR-066 标准化启动参数。

        必传 6 个 argv：
          --run-id / --session-id / --user-id
          --callback-url / --callback-secret / --redis-url
        可选：
          --resume-from-step=N        (coordinator 恢复)
          --otel-trace-id=traceparent (OTel 跨进程传播)
        """
        cmd = [
            "python", "-m", "executor",
            f"--run-id={run.id}",
            f"--session-id={run.session_id}",
            f"--user-id={run.user_id}",
            f"--callback-url=http://backend:8000/api/v1/internal/callbacks",
            f"--callback-secret={self._settings.CALLBACK_SECRET}",
            f"--redis-url={self._settings.REDIS_URL}",
        ]
        if resume_from_step is not None:
            cmd.append(f"--resume-from-step={resume_from_step}")
        # OTel trace propagation: inject current W3C traceparent (ADR-117)
        # get_traceparent() reads from the currently-active OTel span context so
        # the executor subprocess continues the same distributed trace.
        try:
            from app.observability.tracing import get_traceparent
            traceparent = get_traceparent()
        except Exception:
            traceparent = None
        if traceparent:
            cmd.append(f"--otel-trace-id={traceparent}")
        return cmd

    def _build_env(self) -> dict[str, str]:
        """
        ADR-066：传递必要环境变量。

        ENCRYPTION_KEY 和 OTEL_EXPORTER_OTLP_ENDPOINT 通过环境变量注入，
        不放入 argv（避免出现在 ps / 日志中）。
        """
        env = {**os.environ}
        env["ENCRYPTION_KEY"] = self._settings.ENCRYPTION_KEY
        env["OTEL_EXPORTER_OTLP_ENDPOINT"] = self._settings.OTEL_EXPORTER_OTLP_ENDPOINT or ""
        env["BACKEND_URL"] = self._settings.BACKEND_URL
        return env

    # ------------------------------------------------------------------
    # Internal: DB write-back + HTTP notification
    # ------------------------------------------------------------------

    def _mark_running(self, run_id: str, pid: int) -> None:
        """
        写 subprocess_pid 到 runs 表，并调用 RunLifecycle.mark_running()。

        独立 DB session（不阻塞主事务）。
        """
        from app.core.database import SessionLocal
        from app.services.run_lifecycle import RunLifecycle

        try:
            with SessionLocal() as db:
                lifecycle = RunLifecycle(db)
                lifecycle.mark_running(run_id, pid=pid)
                db.commit()
                logger.info(
                    "process_manager.mark_running",
                    run_id=run_id,
                    pid=pid,
                )
        except Exception as exc:
            logger.error(
                "process_manager.mark_running_failed",
                run_id=run_id,
                pid=pid,
                error=str(exc),
            )

    def _notify_timeout(self, run_id: str) -> None:
        """通过 HTTP 回调通知 Backend 超时（run_error 事件）。"""
        self._post_callback(
            run_id=run_id,
            event_type="run_error",
            data={
                "run_id": run_id,
                "error": f"Timeout after {self._settings.RUN_TIMEOUT_SECONDS}s",
            },
        )

    def _notify_failure(self, run_id: str, error: str) -> None:
        """通知非正常退出（run_error 事件）。"""
        self._post_callback(
            run_id=run_id,
            event_type="run_error",
            data={
                "run_id": run_id,
                "error": error,
            },
        )

    def _post_callback(
        self,
        run_id: str,
        event_type: str,
        data: dict,
    ) -> None:
        """
        向内部回调端点发送事件（同步 httpx，在后台线程中调用）。

        重试逻辑：最多 3 次，间隔 1s。
        失败时只记录日志，不抛异常（后台线程容错）。
        """
        url = "http://localhost:8000/api/v1/internal/callbacks"
        payload = {
            "run_id": run_id,
            "event_type": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        headers = {"X-Callback-Secret": self._settings.CALLBACK_SECRET}

        for attempt in range(1, 4):
            try:
                resp = httpx.post(url, json=payload, headers=headers, timeout=5.0)
                resp.raise_for_status()
                logger.info(
                    "process_manager.callback_sent",
                    run_id=run_id,
                    event_type=event_type,
                    attempt=attempt,
                )
                return
            except Exception as exc:
                logger.warning(
                    "process_manager.callback_failed",
                    run_id=run_id,
                    event_type=event_type,
                    attempt=attempt,
                    error=str(exc),
                )
                if attempt < 3:
                    import time
                    time.sleep(1.0)
