from __future__ import annotations

import argparse
import os
from dataclasses import dataclass

import structlog
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import create_engine, text

logger = structlog.get_logger()

MAX_TURNS: dict[str, int] = {
    "chat": 50,
    "explore": 30,
    "build": 100,
    "coordinator": 200,
    "verifier": 20,
    "plugin_builder": 40,
}


@dataclass
class RunConfig:
    run_id: str
    session_id: str
    user_id: str
    callback_url: str
    callback_secret: str
    redis_url: str
    prompt: str
    model: str
    api_key: str
    base_url: str
    agent_type: str
    system_prompt: str
    max_turns: int
    resume_from_step: int | None
    workspace_path: str


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    p.add_argument("--session-id", required=True)
    p.add_argument("--user-id", required=True)
    p.add_argument("--callback-url", required=True)
    p.add_argument("--callback-secret", required=True)
    p.add_argument("--redis-url", required=True)
    p.add_argument("--resume-from-step", type=int, default=None)
    p.add_argument("--otel-trace-id", type=str, default=None)
    return p.parse_args()


def decrypt_api_key(envelope: str, encryption_key_hex: str) -> str:
    parts = envelope.split(":", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid envelope format: {envelope[:20]!r}")
    nonce = bytes.fromhex(parts[0])
    ciphertext = bytes.fromhex(parts[1])
    key = bytes.fromhex(encryption_key_hex)
    return AESGCM(key).decrypt(nonce, ciphertext, None).decode()


def load_run_config(args: argparse.Namespace) -> RunConfig:
    db_url = os.environ["DATABASE_URL"]
    encryption_key = os.environ["ENCRYPTION_KEY"]

    engine = create_engine(db_url, pool_size=1, max_overflow=0)
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT r.prompt, r.model, r.agent_type,
                           p.base_url, p.api_key_encrypted, p.model_id
                      FROM runs r
                      LEFT JOIN providers p ON p.id = r.provider_id
                     WHERE r.id = :run_id
                """),
                {"run_id": args.run_id},
            ).mappings().one()
    finally:
        engine.dispose()

    agent_type = row["agent_type"] or "chat"

    if row["api_key_encrypted"]:
        api_key = decrypt_api_key(row["api_key_encrypted"], encryption_key)
        base_url = row["base_url"]
        model = row["model_id"] or row["model"]
    else:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
        model = row["model"] or "claude-sonnet-4-6-20251101"

    log = logger.bind(run_id=args.run_id, agent_type=agent_type)
    log.info("run_config_loaded")

    return RunConfig(
        run_id=args.run_id,
        session_id=args.session_id,
        user_id=args.user_id,
        callback_url=args.callback_url,
        callback_secret=args.callback_secret,
        redis_url=args.redis_url,
        prompt=row["prompt"],
        model=model,
        api_key=api_key,
        base_url=base_url,
        agent_type=agent_type,
        system_prompt="",
        max_turns=MAX_TURNS.get(agent_type, MAX_TURNS["chat"]),
        resume_from_step=args.resume_from_step,
        workspace_path=os.environ.get("WORKSPACE_PATH", "/tmp"),
    )
