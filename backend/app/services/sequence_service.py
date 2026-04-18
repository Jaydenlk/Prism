"""
Prism v2 — sequence_no 并发原子性 (DOC-07 Task 7.2 ADR-060)

提供两种方案为 messages.sequence_no 和 session_queue_items.sequence_no
安全地分配单调递增序列号，避免 max+1 竞态问题。

⚠️ 陷阱 #6（CLAUDE.md）:
   禁止使用 MAX(sequence_no)+1 直接赋值，必须使用以下两种方案之一。

方案 1（推荐）: PostgreSQL per-session 独立序列
  - CREATE SEQUENCE IF NOT EXISTS "messages_seq_{session_id}"
  - SELECT nextval(...)
  - 优势：完全原子，无锁冲突

方案 2（备选）: advisory_xact_lock + max+1
  - SELECT pg_advisory_xact_lock(hash_key) — 持有至 tx commit
  - 优势：无需建对象，兼容性好
  - 缺点：全局锁粒度较粗（同一 session 串行化）
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def get_next_message_sequence_no(db: Session, session_id: str) -> int:
    """
    方案 1（推荐）：PostgreSQL per-session 独立序列。

    序列名规则: messages_seq_{session_id}，session_id 中 '-' 替换为 '_'
    首次调用时自动创建序列（IF NOT EXISTS 保证幂等）。

    必须在活跃事务内调用，确保 nextval 和后续 INSERT 在同一 tx 中。
    """
    seq_name = f"messages_seq_{session_id.replace('-', '_')}"
    # CREATE SEQUENCE 是 DDL，需在独立语句中执行。
    # autocommit=False 时 CREATE SEQUENCE IF NOT EXISTS 在 tx 中是安全的。
    db.execute(text(f'CREATE SEQUENCE IF NOT EXISTS "{seq_name}"'))
    result = db.execute(text("SELECT nextval(:name)"), {"name": seq_name})
    return result.scalar()  # type: ignore[return-value]


def get_next_message_sequence_no_advisory(db: Session, session_id: str) -> int:
    """
    方案 2（备选）：advisory_xact_lock + COALESCE(MAX,0)+1。

    lock key = (session_id hex bytes 前 8 字节) mod 2^63
    锁在当前事务 commit/rollback 时自动释放。

    使用场景：目标 PG 实例不允许 DDL（如 RDS 权限受限）时使用此方案。
    """
    lock_key = (
        int.from_bytes(
            session_id.replace("-", "")[:16].encode("ascii"), "big"
        )
        % (2**63)
    )
    db.execute(
        text("SELECT pg_advisory_xact_lock(:k)"),
        {"k": lock_key},
    )
    max_seq = db.execute(
        text(
            "SELECT COALESCE(MAX(sequence_no), 0) FROM messages"
            " WHERE session_id = :sid"
        ),
        {"sid": session_id},
    ).scalar()
    return (max_seq or 0) + 1


def get_next_queue_sequence_no(db: Session, session_id: str) -> int:
    """
    session_queue_items.sequence_no 原子分配。

    使用 advisory_xact_lock 方案（队列 item 并发度低，无需专属序列）。
    lock key 在 messages 的 advisory lock 基础上偏移 2^32 以避免冲突。
    """
    lock_key = (
        int.from_bytes(
            session_id.replace("-", "")[:16].encode("ascii"), "big"
        )
        % (2**63)
        + 2**32
    ) % (2**63)
    db.execute(
        text("SELECT pg_advisory_xact_lock(:k)"),
        {"k": lock_key},
    )
    max_seq = db.execute(
        text(
            "SELECT COALESCE(MAX(sequence_no), 0) FROM session_queue_items"
            " WHERE session_id = :sid"
        ),
        {"sid": session_id},
    ).scalar()
    return (max_seq or 0) + 1
