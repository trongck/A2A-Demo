"""
Shared memory repository sử dụng SQLite.
Bám sát mục 6 của V-AI-Implementation-Plan.md.
"""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DB_PATH = DB_DIR / "memory.sqlite"


def get_current_iso_time() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db() -> None:
    """Khởi tạo cấu trúc các bảng theo tài liệu thiết kế."""
    with get_connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            scenario_id TEXT NOT NULL DEFAULT 'base',
            profile_json TEXT NOT NULL DEFAULT '{}',
            demo_clock TEXT NOT NULL DEFAULT '2026-09-18T14:00:00+07:00',
            memory_version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            turn_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            turn_id TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            request_id TEXT NOT NULL,
            a2a_task_id TEXT,
            status TEXT NOT NULL,
            input_version INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS agent_results (
            result_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            turn_id TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            data_revision TEXT NOT NULL,
            result_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS plans (
            plan_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            turn_id TEXT NOT NULL,
            plan_json TEXT NOT NULL,
            is_selected INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            turn_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            sender TEXT NOT NULL,
            receiver TEXT NOT NULL,
            summary TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            duration_ms INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'info',
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
        );
        """)
        conn.commit()


# --- Session Operations ---

def get_or_create_session(session_id: str, scenario_id: str = "base") -> dict[str, Any]:
    init_db()
    now = get_current_iso_time()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        if row:
            return {
                "session_id": row["session_id"],
                "scenario_id": row["scenario_id"],
                "profile": json.loads(row["profile_json"]),
                "demo_clock": row["demo_clock"],
                "memory_version": row["memory_version"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        # Tạo mới
        conn.execute(
            """
            INSERT INTO sessions (session_id, scenario_id, profile_json, demo_clock, memory_version, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, scenario_id, "{}", "2026-09-18T14:00:00+07:00", 1, now, now),
        )
        conn.commit()
        return {
            "session_id": session_id,
            "scenario_id": scenario_id,
            "profile": {},
            "demo_clock": "2026-09-18T14:00:00+07:00",
            "memory_version": 1,
            "created_at": now,
            "updated_at": now,
        }


def update_session(session_id: str, profile: dict[str, Any] | None = None, scenario_id: str | None = None) -> int:
    """Cập nhật session profile hoặc scenario_id, tự động tăng memory_version."""
    now = get_current_iso_time()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        if not row:
            get_or_create_session(session_id, scenario_id or "base")
            row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()

        new_version = row["memory_version"] + 1
        new_scenario = scenario_id if scenario_id is not None else row["scenario_id"]
        
        current_profile = json.loads(row["profile_json"])
        if profile is not None:
            # Merge profile
            current_profile.update(profile)

        conn.execute(
            """
            UPDATE sessions
            SET profile_json = ?, scenario_id = ?, memory_version = ?, updated_at = ?
            WHERE session_id = ?
            """,
            (json.dumps(current_profile, ensure_ascii=False), new_scenario, new_version, now, session_id),
        )
        conn.commit()
        return new_version


# --- Message Operations ---

def add_message(session_id: str, turn_id: str, role: str, content: str) -> None:
    now = get_current_iso_time()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO messages (session_id, turn_id, role, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, turn_id, role, content, now),
        )
        conn.commit()


def get_messages(session_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
        return [
            {
                "id": r["id"],
                "session_id": r["session_id"],
                "turn_id": r["turn_id"],
                "role": r["role"],
                "content": r["content"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]


# --- Event Logging Operations ---

def record_event(
    session_id: str,
    turn_id: str,
    event_type: str,
    sender: str,
    receiver: str,
    summary: str,
    payload: dict[str, Any] | None = None,
    duration_ms: int = 0,
    status: str = "info",
) -> str:
    event_id = f"evt_{uuid.uuid4().hex[:10]}"
    now = get_current_iso_time()
    payload_str = json.dumps(payload or {}, ensure_ascii=False)
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO events (event_id, session_id, turn_id, event_type, sender, receiver, summary, payload_json, duration_ms, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (event_id, session_id, turn_id, event_type, sender, receiver, summary, payload_str, duration_ms, status, now),
        )
        conn.commit()
    return event_id


def get_events(session_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM events WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
        return [
            {
                "event_id": r["event_id"],
                "session_id": r["session_id"],
                "turn_id": r["turn_id"],
                "event_type": r["event_type"],
                "sender": r["sender"],
                "receiver": r["receiver"],
                "summary": r["summary"],
                "payload": json.loads(r["payload_json"]),
                "duration_ms": r["duration_ms"],
                "status": r["status"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]


# --- Agent Results Operations ---

def save_agent_result(
    session_id: str,
    turn_id: str,
    agent_name: str,
    result_data: dict[str, Any],
    data_revision: str = "v1",
) -> str:
    result_id = f"res_{uuid.uuid4().hex[:10]}"
    now = get_current_iso_time()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO agent_results (result_id, session_id, turn_id, agent_name, data_revision, result_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (result_id, session_id, turn_id, agent_name, data_revision, json.dumps(result_data, ensure_ascii=False), now),
        )
        conn.commit()
    return result_id


def get_latest_agent_result(session_id: str, agent_name: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM agent_results
            WHERE session_id = ? AND agent_name = ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (session_id, agent_name),
        ).fetchone()
        if row:
            return json.loads(row["result_json"])
        return None


# --- Plans Operations ---

def save_plans(session_id: str, turn_id: str, plan_data: dict[str, Any]) -> str:
    plan_id = f"plan_{uuid.uuid4().hex[:10]}"
    now = get_current_iso_time()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO plans (plan_id, session_id, turn_id, plan_json, is_selected, created_at)
            VALUES (?, ?, ?, ?, 0, ?)
            """,
            (plan_id, session_id, turn_id, json.dumps(plan_data, ensure_ascii=False), now),
        )
        conn.commit()
    return plan_id


def get_latest_plans(session_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM plans
            WHERE session_id = ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (session_id,),
        ).fetchone()
        if row:
            return json.loads(row["plan_json"])
        return None
