"""Tiny SQLite document store: one JSON document per session."""
import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path

DB_PATH = Path(os.getenv("DAYZERO_DB", Path(__file__).resolve().parent.parent / "dayzero.db"))
_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, doc TEXT NOT NULL, updated REAL NOT NULL)"
    )
    return conn


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def save(doc: dict) -> None:
    with _lock, _conn() as c:
        c.execute(
            "INSERT INTO sessions(id, doc, updated) VALUES(?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET doc=excluded.doc, updated=excluded.updated",
            (doc["id"], json.dumps(doc, ensure_ascii=False), time.time()),
        )


def load(session_id: str) -> dict | None:
    with _lock, _conn() as c:
        row = c.execute("SELECT doc FROM sessions WHERE id=?", (session_id,)).fetchone()
    return json.loads(row[0]) if row else None


def list_all() -> list[dict]:
    with _lock, _conn() as c:
        rows = c.execute("SELECT doc FROM sessions ORDER BY updated DESC").fetchall()
    return [json.loads(r[0]) for r in rows]
