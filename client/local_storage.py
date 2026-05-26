"""Local SQLite buffer — holds sessions until they are successfully uploaded."""

import sqlite3
import uuid
from pathlib import Path


class LocalStorage:
    def __init__(self, config: dict) -> None:
        db_path = Path(config.get("storage", {}).get("db_path", "sessions.db"))
        db_path = db_path.expanduser()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id              INTEGER PRIMARY KEY,
                session_uuid    TEXT UNIQUE NOT NULL,
                start           TEXT NOT NULL,
                end             TEXT NOT NULL,
                app             TEXT NOT NULL,
                title           TEXT NOT NULL,
                duration_seconds INTEGER NOT NULL,
                uploaded        INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_uploaded ON sessions(uploaded);
            """
        )
        self._conn.commit()

    def save_session(self, s: dict) -> None:
        session_uuid = s.get("session_uuid") or str(uuid.uuid4())
        self._conn.execute(
            """INSERT OR IGNORE INTO sessions
               (session_uuid, start, end, app, title, duration_seconds)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                session_uuid,
                s["start"],
                s["end"],
                s["app"],
                s["title"],
                s["duration_seconds"],
            ),
        )
        self._conn.commit()

    def get_pending(self, limit: int = 500) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM sessions WHERE uploaded = 0 ORDER BY start LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_uploaded(self, ids: list[int]) -> None:
        if not ids:
            return
        placeholders = ",".join("?" * len(ids))
        self._conn.execute(
            f"UPDATE sessions SET uploaded = 1 WHERE id IN ({placeholders})", ids
        )
        self._conn.commit()
