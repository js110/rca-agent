"""PR 分析状态（sqlite 持久化）：head_sha 去重 + sticky 评论定位。"""

from __future__ import annotations

import sqlite3
import threading
import time

from . import config


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(config.STATE_DB), timeout=30)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS pr_state ("
        "repo TEXT NOT NULL, pr INTEGER NOT NULL, head_sha TEXT NOT NULL, "
        "comment_id INTEGER, analyzed_at REAL, "
        "PRIMARY KEY (repo, pr))"
    )
    return conn


def get(repo: str, pr: int) -> dict | None:
    """返回 {head_sha, comment_id}；从未分析过返回 None。"""
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT head_sha, comment_id FROM pr_state WHERE repo=? AND pr=?",
            (repo, pr),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {"head_sha": row[0], "comment_id": row[1]}


def put(repo: str, pr: int, head_sha: str, comment_id: int | None = None) -> None:
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO pr_state (repo, pr, head_sha, comment_id, analyzed_at) "
            "VALUES (?,?,?,?,?) "
            "ON CONFLICT (repo, pr) DO UPDATE SET "
            "head_sha=excluded.head_sha, comment_id=excluded.comment_id, "
            "analyzed_at=excluded.analyzed_at",
            (repo, pr, head_sha, comment_id, time.time()),
        )
        conn.commit()
    finally:
        conn.close()
