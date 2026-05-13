from __future__ import annotations

import threading
import time

import redis
import structlog

log = structlog.get_logger(__name__)


def start_heartbeat_thread(
    redis_url: str,
    run_id: str,
    interval: int = 5,
    ttl: int = 60,
) -> threading.Event:
    stop = threading.Event()
    t = threading.Thread(
        target=_heartbeat_loop,
        args=(redis_url, run_id, stop, interval, ttl),
        daemon=True,
        name=f"heartbeat-{run_id[:8]}",
    )
    t.start()
    return stop


def _heartbeat_loop(
    redis_url: str,
    run_id: str,
    stop: threading.Event,
    interval: int,
    ttl: int,
) -> None:
    key = f"harness:heartbeat:{run_id}"
    client = redis.from_url(redis_url)
    try:
        while not stop.is_set():
            try:
                client.setex(key, ttl, str(int(time.time())))
            except Exception as exc:
                log.warning("heartbeat.write_failed", run_id=run_id, error=str(exc))
            stop.wait(timeout=interval)
    finally:
        try:
            client.delete(key)
        except Exception:
            pass
        client.close()
