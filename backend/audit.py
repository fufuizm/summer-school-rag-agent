"""
Audit Log - Immutable record of all agent actions.
Uses SQLite for persistence.
"""

import json
import sqlite3
from datetime import datetime, timezone


class AuditLog:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                action TEXT NOT NULL,
                target TEXT NOT NULL,
                details TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()

    def log(self, action: str, target: str, details: dict = None):
        """Log an action to the audit trail."""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO audit_log (timestamp, action, target, details) VALUES (?, ?, ?, ?)",
            (
                datetime.now(timezone.utc).isoformat(),
                action,
                target,
                json.dumps(details, default=str) if details else None,
            ),
        )
        conn.commit()
        conn.close()

    def get_recent(self, limit: int = 50) -> list[dict]:
        """Retrieve recent audit log entries."""
        limit = max(1, min(int(limit), 200))
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()

        return [
            {
                "id": row["id"],
                "timestamp": row["timestamp"],
                "action": row["action"],
                "target": row["target"],
                "details": json.loads(row["details"]) if row["details"] else None,
            }
            for row in rows
        ]

    def get_by_action(self, action: str, limit: int = 50) -> list[dict]:
        """Retrieve audit entries filtered by action type."""
        limit = max(1, min(int(limit), 200))
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE action = ? ORDER BY id DESC LIMIT ?",
            (action, limit),
        ).fetchall()
        conn.close()

        return [
            {
                "id": row["id"],
                "timestamp": row["timestamp"],
                "action": row["action"],
                "target": row["target"],
                "details": json.loads(row["details"]) if row["details"] else None,
            }
            for row in rows
        ]
