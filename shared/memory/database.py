"""
Shared memory repository sử dụng SQLite.
Bám sát mục 6 của V-AI-Implementation-Plan.md.
"""

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

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

        -- Admin Portal tables
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'coordinator',
            is_active INTEGER NOT NULL DEFAULT 1,
            last_login_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """)

        # Backward-compat: thêm cột admin tracking vào plans nếu chưa có
        _ensure_column(conn, "plans", "admin_status", "TEXT NOT NULL DEFAULT 'pending'")
        _ensure_column(conn, "plans", "admin_note", "TEXT")
        _ensure_column(conn, "plans", "admin_confirmed_by", "TEXT")
        _ensure_column(conn, "plans", "admin_confirmed_at", "TEXT")

        # Backward-compat: thêm cột admin_status vào sessions
        _ensure_column(conn, "sessions", "admin_status", "TEXT NOT NULL DEFAULT 'pending'")
        _ensure_column(conn, "sessions", "admin_reject_reason", "TEXT")

        conn.commit()

    # Seed default admin account
    seed_admin_users()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, col_def: str) -> None:
    """Thêm cột vào bảng nếu chưa tồn tại (idempotent)."""
    existing = conn.execute(f"PRAGMA table_info({table})").fetchall()
    col_names = [r["name"] for r in existing]
    if column not in col_names:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")


def seed_admin_users() -> None:
    """Seed hoặc đồng bộ tài khoản admin từ biến môi trường .env."""
    load_dotenv(dotenv_path=ENV_PATH, override=True)
    username = os.environ.get("ADMIN_USERNAME", "").strip()
    password = os.environ.get("ADMIN_PASSWORD", "")
    display_name = os.environ.get("ADMIN_DISPLAY_NAME", "Điều phối viên V-AI")
    if not username or not password:
        return

    try:
        from shared.admin_auth.auth import hash_password as _hash
    except Exception:
        return  # bcrypt chưa cài — skip silently

    now = get_current_iso_time()
    with get_connection() as conn:
        existing = conn.execute("SELECT * FROM admin_users WHERE username = ?", (username,)).fetchone()
        pw_hash = _hash(password)
        if not existing:
            conn.execute(
                """
                INSERT INTO admin_users (username, password_hash, display_name, role, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    username,
                    pw_hash,
                    display_name,
                    "coordinator",
                    now,
                    now,
                ),
            )
            conn.commit()
        else:
            # Luôn cập nhật hash mật khẩu và tên hiển thị mới nhất theo .env
            conn.execute(
                """
                UPDATE admin_users
                SET password_hash = ?, display_name = ?, updated_at = ?
                WHERE username = ?
                """,
                (pw_hash, display_name, now, username),
            )
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
                "memory_version": row["memory_version"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        # Tạo mới
        conn.execute(
            """
            INSERT INTO sessions (session_id, scenario_id, profile_json, memory_version, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, scenario_id, "{}", 1, now, now),
        )
        conn.commit()
        return {
            "session_id": session_id,
            "scenario_id": scenario_id,
            "profile": {},
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
    data_revision: str = "google_places_v2",
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


def get_all_plans_for_session(session_id: str) -> list[dict[str, Any]]:
    """Lấy tất cả plan records (có admin metadata) của một session."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM plans WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
        result = []
        for r in rows:
            plans_list = json.loads(r["plan_json"])
            result.append({
                "plan_id": r["plan_id"],
                "session_id": r["session_id"],
                "turn_id": r["turn_id"],
                "plans": plans_list if isinstance(plans_list, list) else [plans_list],
                "is_selected": bool(r["is_selected"]),
                "admin_status": r["admin_status"] if "admin_status" in r.keys() else "pending",
                "admin_note": r["admin_note"] if "admin_note" in r.keys() else None,
                "admin_confirmed_by": r["admin_confirmed_by"] if "admin_confirmed_by" in r.keys() else None,
                "admin_confirmed_at": r["admin_confirmed_at"] if "admin_confirmed_at" in r.keys() else None,
                "created_at": r["created_at"],
            })
        return result


# --- Admin Operations ---

def get_admin_user(username: str) -> dict[str, Any] | None:
    """Lấy thông tin admin user theo username."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM admin_users WHERE username = ? AND is_active = 1",
            (username,),
        ).fetchone()
        if row:
            return {
                "id": row["id"],
                "username": row["username"],
                "password_hash": row["password_hash"],
                "display_name": row["display_name"],
                "role": row["role"],
                "is_active": bool(row["is_active"]),
                "last_login_at": row["last_login_at"],
                "created_at": row["created_at"],
            }
        return None


def update_admin_last_login(username: str) -> None:
    """Cập nhật thời gian đăng nhập gần nhất."""
    now = get_current_iso_time()
    with get_connection() as conn:
        conn.execute(
            "UPDATE admin_users SET last_login_at = ?, updated_at = ? WHERE username = ?",
            (now, now, username),
        )
        conn.commit()


def get_all_sessions_summary(
    admin_status_filter: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """Lấy danh sách tóm tắt sessions cho trang Bookings của Admin."""
    with get_connection() as conn:
        where_clauses = []
        params: list[Any] = []
        if admin_status_filter and admin_status_filter != "all":
            where_clauses.append("s.admin_status = ?")
            params.append(admin_status_filter)

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        total_row = conn.execute(
            f"SELECT COUNT(*) as c FROM sessions s {where_sql}", params
        ).fetchone()
        total = total_row["c"] if total_row else 0

        offset = (page - 1) * page_size
        rows = conn.execute(
            f"""
            SELECT s.session_id, s.scenario_id, s.profile_json, s.memory_version,
                   s.admin_status, s.admin_reject_reason,
                   s.created_at, s.updated_at,
                   (
                     SELECT COUNT(*) FROM plans p WHERE p.session_id = s.session_id
                   ) as plan_count,
                   (
                     SELECT content FROM messages m
                     WHERE m.session_id = s.session_id AND m.role = 'user'
                     ORDER BY m.id DESC LIMIT 1
                   ) as last_user_message
            FROM sessions s
            {where_sql}
            ORDER BY s.updated_at DESC
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        ).fetchall()

        items = []
        for r in rows:
            profile = json.loads(r["profile_json"] or "{}")
            group_members = profile.get("group_members", [])
            items.append({
                "session_id": r["session_id"],
                "scenario_id": r["scenario_id"],
                "admin_status": r["admin_status"] or "pending",
                "admin_reject_reason": r["admin_reject_reason"],
                "group_size": len(group_members),
                "plan_count": r["plan_count"],
                "memory_version": r["memory_version"],
                "last_message_preview": (r["last_user_message"] or "")[:100],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            })

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": items,
        }


def admin_confirm_plan(
    session_id: str,
    plan_id: str,
    note: str | None,
    confirmed_by: str,
) -> bool:
    """Xác nhận 1 plan cụ thể, đánh dấu admin_status = confirmed."""
    now = get_current_iso_time()
    with get_connection() as conn:
        # Cập nhật plan được chọn
        conn.execute(
            """
            UPDATE plans SET
                admin_status = 'confirmed',
                is_selected = 1,
                admin_note = ?,
                admin_confirmed_by = ?,
                admin_confirmed_at = ?
            WHERE plan_id = ? AND session_id = ?
            """,
            (note, confirmed_by, now, plan_id, session_id),
        )
        # Cập nhật admin_status của session
        conn.execute(
            "UPDATE sessions SET admin_status = 'confirmed', updated_at = ? WHERE session_id = ?",
            (now, session_id),
        )
        conn.commit()
    return True


def admin_reject_session(session_id: str, reason: str) -> bool:
    """Từ chối toàn bộ phiên đặt lịch."""
    now = get_current_iso_time()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE sessions SET
                admin_status = 'rejected',
                admin_reject_reason = ?,
                updated_at = ?
            WHERE session_id = ?
            """,
            (reason, now, session_id),
        )
        conn.commit()
    return True


def get_admin_booking_stats() -> dict[str, Any]:
    """Thống kê tổng hợp cho Dashboard của Admin."""
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) as c FROM sessions").fetchone()["c"]
        pending = conn.execute(
            "SELECT COUNT(*) as c FROM sessions WHERE admin_status = 'pending'"
        ).fetchone()["c"]
        confirmed = conn.execute(
            "SELECT COUNT(*) as c FROM sessions WHERE admin_status = 'confirmed'"
        ).fetchone()["c"]
        rejected = conn.execute(
            "SELECT COUNT(*) as c FROM sessions WHERE admin_status = 'rejected'"
        ).fetchone()["c"]
        plan_count = conn.execute("SELECT COUNT(*) as c FROM plans").fetchone()["c"]
        return {
            "total_sessions": total,
            "pending": pending,
            "confirmed": confirmed,
            "rejected": rejected,
            "total_plans": plan_count,
        }
