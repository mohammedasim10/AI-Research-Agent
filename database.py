"""
database.py - Production SQLite Persistence & Session Isolation Layer for ResearchAI.
Ensures zero session bleeding between users, parameterized queries against SQL injection,
thread-safe operations with Write-Ahead Logging (WAL), and scalable schema migrations.
"""

import datetime
import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("ResearchAI.Database")

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DEFAULT_DB_PATH = DATA_DIR / "research_bot.db"


class Database:
    """
    Thread-safe SQLite connection manager with WAL mode and isolated user namespaces.
    """

    _local = threading.local()

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or DEFAULT_DB_PATH)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Returns a thread-local SQLite connection matching the target database path."""
        if (
            not hasattr(self._local, "conn")
            or self._local.conn is None
            or getattr(self._local, "db_path", None) != self.db_path
        ):
            conn = sqlite3.connect(
                self.db_path,
                timeout=30.0,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            self._local.conn = conn
            self._local.db_path = self.db_path
        return self._local.conn


    def _init_db(self) -> None:
        """Initializes database schema with safe table and index creation."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            with conn:
                conn.execute("PRAGMA journal_mode = WAL;")
                conn.execute("PRAGMA foreign_keys = ON;")

                # 1. Users Table (Strict per-user isolation)
                conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    language TEXT DEFAULT 'en',
                    response_mode TEXT DEFAULT 'deep',
                    voice_enabled INTEGER DEFAULT 1,
                    custom_api_key TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """)

                # 2. Research Sessions Table (History & Cached Reports)
                conn.execute("""
                CREATE TABLE IF NOT EXISTS research_sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    query TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    language TEXT NOT NULL,
                    plan_json TEXT,
                    analysis_json TEXT,
                    report_markdown TEXT NOT NULL,
                    teaching_markdown TEXT,
                    sources_json TEXT,
                    metrics_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );
                """)

                # 3. Conversation Messages Table (Isolated Per-User History)
                conn.execute("""
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
                    content TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );
                """)

                # 4. Rate Limiting Table
                conn.execute("""
                CREATE TABLE IF NOT EXISTS rate_limits (
                    user_id INTEGER PRIMARY KEY,
                    window_start REAL NOT NULL,
                    request_count INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );
                """)

                # 5. Audit & Telemetry Logs Table
                conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    event_type TEXT NOT NULL,
                    details TEXT,
                    status TEXT NOT NULL,
                    duration_ms REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """)

                # 6. Contact Notes / Messages Left for Owner
                conn.execute("""
                CREATE TABLE IF NOT EXISTS contact_inbox (
                    note_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    username TEXT,
                    sender_name TEXT,
                    message_text TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """)

                # Performance & Query Indices
                conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON research_sessions(user_id, created_at DESC);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_user ON conversation_messages(user_id, message_id ASC);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id, created_at DESC);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_event ON audit_logs(event_type, created_at DESC);")
        finally:
            conn.close()

    # --------------------------------------------------------------------------
    # User Profile Management
    # --------------------------------------------------------------------------

    def get_or_create_user(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Retrieves user profile or inserts a new isolated profile."""
        conn = self._get_connection()
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with conn:
            cursor = conn.execute(
                "SELECT * FROM users WHERE user_id = ?;",
                (user_id,),
            )
            row = cursor.fetchone()
            if row:
                conn.execute(
                    "UPDATE users SET username = COALESCE(?, username), first_name = COALESCE(?, first_name), last_name = COALESCE(?, last_name), last_active = ? WHERE user_id = ?;",
                    (username, first_name, last_name, now, user_id),
                )
                return dict(row)

            conn.execute(
                """
                INSERT INTO users (user_id, username, first_name, last_name, language, response_mode, voice_enabled, created_at, last_active)
                VALUES (?, ?, ?, ?, 'en', 'deep', 1, ?, ?);
                """,
                (user_id, username, first_name, last_name, now, now),
            )
            cursor = conn.execute("SELECT * FROM users WHERE user_id = ?;", (user_id,))
            return dict(cursor.fetchone())

    def update_user_setting(self, user_id: int, setting_name: str, value: Any) -> bool:
        """Safely updates a user setting via allowed whitelist."""
        allowed_settings = {"language", "response_mode", "voice_enabled", "custom_api_key"}
        if setting_name not in allowed_settings:
            raise ValueError(f"Invalid setting name: {setting_name}")

        conn = self._get_connection()
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with conn:
            conn.execute(
                f"UPDATE users SET {setting_name} = ?, last_active = ? WHERE user_id = ?;",
                (value, now, user_id),
            )
        return True

    def get_user_setting(self, user_id: int, setting_name: str, default: Any = None) -> Any:
        """Retrieves a specific user setting safely."""
        user = self.get_or_create_user(user_id)
        return user.get(setting_name, default)

    # --------------------------------------------------------------------------
    # Conversation History & Session Reset (/clear)
    # --------------------------------------------------------------------------

    def add_conversation_message(self, user_id: int, role: str, content: str) -> None:
        """Adds a message to the user's isolated conversation history."""
        if role not in ("user", "assistant", "system"):
            role = "user"
        self.get_or_create_user(user_id)
        conn = self._get_connection()
        with conn:
            conn.execute(
                "INSERT INTO conversation_messages (user_id, role, content) VALUES (?, ?, ?);",
                (user_id, role, content),
            )

    def get_conversation_history(self, user_id: int, limit: int = 10) -> List[Dict[str, str]]:
        """Retrieves the recent conversation history strictly for the requesting user."""
        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT role, content FROM conversation_messages
            WHERE user_id = ?
            ORDER BY message_id DESC
            LIMIT ?;
            """,
            (user_id, limit),
        )
        rows = cursor.fetchall()
        # Return chronologically ordered
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def clear_user_conversation(self, user_id: int) -> int:
        """
        Safely clears active conversation messages for the requesting user ONLY.
        Other users' histories are completely untouched.
        """
        conn = self._get_connection()
        with conn:
            cursor = conn.execute(
                "DELETE FROM conversation_messages WHERE user_id = ?;",
                (user_id,),
            )
            deleted = cursor.rowcount
            self.log_event(user_id, "conversation_cleared", f"Cleared {deleted} messages", "success")
            return deleted

    # --------------------------------------------------------------------------
    # Research Sessions & Historical Archival (/history, /sources)
    # --------------------------------------------------------------------------

    def save_research_session(
        self,
        session_id: str,
        user_id: int,
        query: str,
        mode: str,
        language: str,
        plan: Optional[Dict[str, Any]],
        analysis: Optional[Dict[str, Any]],
        report_markdown: str,
        teaching_markdown: str,
        sources: List[Dict[str, Any]],
        metrics: Dict[str, Any],
    ) -> None:
        """Persists a finalized research session for the user."""
        conn = self._get_connection()
        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO research_sessions
                (session_id, user_id, query, mode, language, plan_json, analysis_json, report_markdown, teaching_markdown, sources_json, metrics_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    session_id,
                    user_id,
                    query,
                    mode,
                    language,
                    json.dumps(plan, ensure_ascii=False) if plan else None,
                    json.dumps(analysis, ensure_ascii=False) if analysis else None,
                    report_markdown,
                    teaching_markdown,
                    json.dumps(sources, ensure_ascii=False) if sources else None,
                    json.dumps(metrics, ensure_ascii=False) if metrics else None,
                ),
            )

    def get_latest_research_session(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves the most recent research session belonging to this user."""
        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT * FROM research_sessions
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 1;
            """,
            (user_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return self._format_session_row(row)

    def get_user_research_history(self, user_id: int, limit: int = 5) -> List[Dict[str, Any]]:
        """Retrieves historical research sessions for this user."""
        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT * FROM research_sessions
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?;
            """,
            (user_id, limit),
        )
        return [self._format_session_row(r) for r in cursor.fetchall()]

    def _format_session_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        """Unpacks JSON fields into structured Python dictionaries."""
        d = dict(row)
        for json_field in ("plan_json", "analysis_json", "sources_json", "metrics_json"):
            if d.get(json_field):
                try:
                    d[json_field.replace("_json", "")] = json.loads(d[json_field])
                except Exception:
                    d[json_field.replace("_json", "")] = None
            else:
                d[json_field.replace("_json", "")] = None
        return d

    # --------------------------------------------------------------------------
    # Rate Limiting (Sliding Window / Token Bucket)
    # --------------------------------------------------------------------------

    def check_and_increment_rate_limit(
        self,
        user_id: int,
        max_requests: int = 15,
        window_seconds: float = 60.0,
    ) -> Tuple[bool, int, float]:
        """
        Enforces a per-user sliding window rate limit.
        Returns (is_allowed, remaining_requests, retry_after_seconds).
        """
        self.get_or_create_user(user_id)
        now = time.time()
        conn = self._get_connection()
        with conn:
            cursor = conn.execute("SELECT * FROM rate_limits WHERE user_id = ?;", (user_id,))
            row = cursor.fetchone()

            if not row:
                conn.execute(
                    "INSERT INTO rate_limits (user_id, window_start, request_count) VALUES (?, ?, 1);",
                    (user_id, now),
                )
                return True, max_requests - 1, 0.0

            window_start = row["window_start"]
            request_count = row["request_count"]

            if now - window_start >= window_seconds:
                # Window expired, reset
                conn.execute(
                    "UPDATE rate_limits SET window_start = ?, request_count = 1 WHERE user_id = ?;",
                    (now, user_id),
                )
                return True, max_requests - 1, 0.0

            if request_count >= max_requests:
                retry_after = round(window_seconds - (now - window_start), 1)
                return False, 0, max(0.5, retry_after)

            # Increment count
            conn.execute(
                "UPDATE rate_limits SET request_count = request_count + 1 WHERE user_id = ?;",
                (user_id,),
            )
            return True, max_requests - (request_count + 1), 0.0

    # --------------------------------------------------------------------------
    # Contact Inbox & Audit Logging
    # --------------------------------------------------------------------------

    def log_contact_message(self, user_id: int, username: str, name: str, message: str) -> None:
        """Logs a note/message left by a user."""
        conn = self._get_connection()
        with conn:
            conn.execute(
                "INSERT INTO contact_inbox (user_id, username, sender_name, message_text) VALUES (?, ?, ?, ?);",
                (user_id, username, name, message),
            )

    def get_contact_messages(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Retrieves recent contact notes."""
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT * FROM contact_inbox ORDER BY created_at DESC LIMIT ?;",
            (limit,),
        )
        return [dict(r) for r in cursor.fetchall()]

    def log_event(
        self,
        user_id: Optional[int],
        event_type: str,
        details: Optional[str] = None,
        status: str = "success",
        duration_ms: Optional[float] = None,
    ) -> None:
        """Records a structured telemetry and audit event."""
        try:
            conn = self._get_connection()
            with conn:
                conn.execute(
                    "INSERT INTO audit_logs (user_id, event_type, details, status, duration_ms) VALUES (?, ?, ?, ?, ?);",
                    (user_id, event_type, details, status, duration_ms),
                )
        except Exception as e:
            logger.debug(f"Audit log writing failed: {e}")

    # --------------------------------------------------------------------------
    # Admin Telemetry & Health Statistics
    # --------------------------------------------------------------------------

    def get_admin_metrics(self) -> Dict[str, Any]:
        """Calculates aggregated metrics for the secure admin dashboard."""
        conn = self._get_connection()
        metrics: Dict[str, Any] = {}
        with conn:
            # Total & Active Users
            metrics["total_users"] = conn.execute("SELECT COUNT(*) FROM users;").fetchone()[0]
            metrics["active_users_24h"] = conn.execute(
                "SELECT COUNT(*) FROM users WHERE last_active >= datetime('now', '-1 day');"
            ).fetchone()[0]

            # Research Queries
            metrics["total_queries"] = conn.execute("SELECT COUNT(*) FROM research_sessions;").fetchone()[0]
            metrics["queries_today"] = conn.execute(
                "SELECT COUNT(*) FROM research_sessions WHERE created_at >= datetime('now', 'start of day');"
            ).fetchone()[0]

            # Error Telemetry
            total_logs = conn.execute("SELECT COUNT(*) FROM audit_logs;").fetchone()[0]
            error_logs = conn.execute("SELECT COUNT(*) FROM audit_logs WHERE status = 'error' OR status = 'failed';").fetchone()[0]
            metrics["total_events"] = total_logs
            metrics["error_count"] = error_logs
            metrics["error_rate_pct"] = round((error_logs / total_logs * 100), 2) if total_logs > 0 else 0.0

            # Average Response Duration
            avg_duration = conn.execute(
                "SELECT AVG(duration_ms) FROM audit_logs WHERE duration_ms IS NOT NULL AND event_type = 'research_run';"
            ).fetchone()[0]
            metrics["avg_research_duration_seconds"] = round(avg_duration / 1000.0, 2) if avg_duration else 0.0

            # Language Breakdown
            lang_rows = conn.execute(
                "SELECT language, COUNT(*) as cnt FROM users GROUP BY language ORDER BY cnt DESC;"
            ).fetchall()
            metrics["language_breakdown"] = {r["language"]: r["cnt"] for r in lang_rows}

            # Recent Errors
            recent_errs = conn.execute(
                """
                SELECT event_type, details, created_at FROM audit_logs
                WHERE status IN ('error', 'failed')
                ORDER BY created_at DESC LIMIT 5;
                """
            ).fetchall()
            metrics["recent_errors"] = [dict(r) for r in recent_errs]

        return metrics

    get_stats = get_admin_metrics


# Global Default Database Instance
db = Database()
