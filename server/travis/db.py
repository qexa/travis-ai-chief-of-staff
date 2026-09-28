"""SQLite data access. Small, explicit, no ORM, so the logic is easy to read and port."""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .settings import REPO_ROOT, get_settings

_SCHEMA = (REPO_ROOT / "database" / "schema.sql").read_text()
_lock = threading.Lock()
_conn: sqlite3.Connection | None = None
_conn_path: str | None = None


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def conn() -> sqlite3.Connection:
    global _conn, _conn_path
    path = get_settings().db_path
    if _conn is None or _conn_path != path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(_SCHEMA)
        _conn_path = path
    return _conn


def reset_connection() -> None:
    global _conn, _conn_path
    if _conn is not None:
        _conn.close()
    _conn, _conn_path = None, None


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    with _lock:
        cur = conn().execute(sql, tuple(params))
        conn().commit()
        return cur.lastrowid or 0


def query(sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    with _lock:
        return [dict(r) for r in conn().execute(sql, tuple(params)).fetchall()]


def one(sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
    rows = query(sql, params)
    return rows[0] if rows else None


# ── contacts ────────────────────────────────────────────────────────────────
def find_contact_by_phone(phone: str) -> dict[str, Any] | None:
    return one("SELECT * FROM contacts WHERE phone = ?", (phone,)) if phone else None


def find_contact_by_name(name: str) -> dict[str, Any] | None:
    if not name:
        return None
    return one("SELECT * FROM contacts WHERE lower(name) = lower(?) ORDER BY call_count DESC", (name.strip(),))


def upsert_contact(name: str, phone: str, company: str = "", tier: str = "known", email: str = "", notes: str = "") -> dict[str, Any]:
    existing = find_contact_by_phone(phone) if phone else find_contact_by_name(name)
    now = utcnow_iso()
    if existing:
        execute(
            "UPDATE contacts SET name = COALESCE(NULLIF(?, ''), name), company = COALESCE(NULLIF(?, ''), company),"
            " email = COALESCE(NULLIF(?, ''), email), call_count = call_count + 1, last_call_at = ? WHERE id = ?",
            (name, company, email, now, existing["id"]),
        )
        return one("SELECT * FROM contacts WHERE id = ?", (existing["id"],)) or existing
    cid = execute(
        "INSERT INTO contacts (name, phone, email, company, tier, notes, call_count, last_call_at, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
        (name or "Unknown caller", phone or None, email, company, tier, notes, now, now),
    )
    return one("SELECT * FROM contacts WHERE id = ?", (cid,)) or {}


def set_contact_tier(contact_id: int, tier: str) -> None:
    execute("UPDATE contacts SET tier = ? WHERE id = ?", (tier, contact_id))


# ── calls / messages / memory / followups / actions / outbox ───────────────
def start_call(call_id: str, caller_phone: str) -> None:
    execute(
        "INSERT OR IGNORE INTO calls (call_id, caller_phone, started_at) VALUES (?, ?, ?)",
        (call_id, caller_phone, utcnow_iso()),
    )


def update_call(call_id: str, **fields: Any) -> None:
    if not call_id or not fields:
        return
    start_call(call_id, fields.get("caller_phone", ""))
    cols = ", ".join(f"{k} = ?" for k in fields)
    execute(f"UPDATE calls SET {cols} WHERE call_id = ?", (*fields.values(), call_id))


def add_message(**m: Any) -> int:
    m.setdefault("created_at", utcnow_iso())
    cols = ", ".join(m)
    marks = ", ".join("?" for _ in m)
    return execute(f"INSERT INTO messages ({cols}) VALUES ({marks})", m.values())


def add_memory(subject: str, fact: str, source: str, visibility: str = "private") -> int:
    return execute(
        "INSERT INTO memories (subject, fact, source, visibility, created_at) VALUES (?, ?, ?, ?, ?)",
        (subject, fact, source, visibility, utcnow_iso()),
    )


def search_memories(text: str, visibility: str | None = None, limit: int = 8) -> list[dict[str, Any]]:
    words = [w for w in text.lower().split() if len(w) > 2][:6] or [text.lower()]
    clause = " OR ".join("lower(subject || ' ' || fact) LIKE ?" for _ in words)
    params: list[Any] = [f"%{w}%" for w in words]
    sql = f"SELECT * FROM memories WHERE ({clause})"
    if visibility:
        sql += " AND visibility = ?"
        params.append(visibility)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    return query(sql, params)


def add_followup(title: str, owner_key: str = "exec", due_at: str | None = None,
                 related_contact: str = "", related_call_id: str = "") -> int:
    return execute(
        "INSERT INTO followups (title, owner_key, due_at, related_contact, related_call_id, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (title, owner_key, due_at, related_contact, related_call_id, utcnow_iso()),
    )


def log_action(actor: str, action: str, detail: str, call_id: str = "") -> None:
    execute(
        "INSERT INTO actions (actor, action, detail, call_id, created_at) VALUES (?, ?, ?, ?, ?)",
        (actor, action, detail, call_id, utcnow_iso()),
    )


def add_outbox(channel: str, recipient: str, body: str, status: str, subject: str = "", error: str = "") -> None:
    execute(
        "INSERT INTO outbox (channel, recipient, subject, body, status, error, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (channel, recipient, subject, body, status, error, utcnow_iso()),
    )


def kv_get(key: str) -> str | None:
    row = one("SELECT value FROM kv WHERE key = ?", (key,))
    return row["value"] if row else None


def kv_set(key: str, value: str) -> None:
    execute("INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
