"""
SQLite storage for issue_key <-> job_id mapping with mode and status tracking.
"""
import sqlite3
from pathlib import Path
from typing import Optional


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS issue_jobs (
            issue_key TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            mode TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_issue_jobs_status ON issue_jobs(status);
        CREATE INDEX IF NOT EXISTS idx_issue_jobs_job_id ON issue_jobs(job_id);
    """)
    conn.commit()


class IssueJobDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db_path) as conn:
            _ensure_schema(conn)

    def _get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    @staticmethod
    def _row_to_dict(row) -> dict:
        return {
            "issue_key": row[0],
            "job_id": row[1],
            "mode": row[2],
            "status": row[3],
            "created_at": row[4] if len(row) > 4 else None,
            "updated_at": row[5] if len(row) > 5 else None,
        }

    def insert(self, issue_key: str, job_id: str, mode: str) -> None:
        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO issue_jobs (issue_key, job_id, mode, status, updated_at) VALUES (?, ?, ?, 'active', datetime('now'))",
                (issue_key, job_id, mode),
            )

    def get_by_issue(self, issue_key: str) -> Optional[dict]:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT issue_key, job_id, mode, status, created_at, updated_at FROM issue_jobs WHERE issue_key = ?",
                (issue_key,),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_by_job_id(self, job_id: str) -> Optional[dict]:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT issue_key, job_id, mode, status, created_at, updated_at FROM issue_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def has_active_job(self, issue_key: str) -> bool:
        row = self.get_by_issue(issue_key)
        return row is not None and row["status"] == "active"

    def update_status(self, issue_key: str, status: str) -> None:
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE issue_jobs SET status = ?, updated_at = datetime('now') WHERE issue_key = ?",
                (status, issue_key),
            )

    def list_active(self) -> list[dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT issue_key, job_id, mode, status FROM issue_jobs WHERE status = 'active'"
            ).fetchall()
        return [
            {"issue_key": r[0], "job_id": r[1], "mode": r[2], "status": r[3]}
            for r in rows
        ]
