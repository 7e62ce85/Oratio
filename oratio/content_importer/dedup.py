"""
Deduplication engine backed by SQLite.

Stores fingerprints (URL hashes) of all previously imported posts
so we never post the same content twice.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone

import config
from models import NormalizedPost

logger = logging.getLogger("content_importer.dedup")


class DedupStore:
    """SQLite-backed dedup + import history store."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or config.DB_PATH
        self._init_db()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS imported_posts (
                    fingerprint TEXT PRIMARY KEY,
                    url         TEXT NOT NULL,
                    title       TEXT,
                    source      TEXT,
                    lemmy_post_id INTEGER,
                    imported_at TEXT NOT NULL,
                    ai_rank     INTEGER,
                    ai_reason   TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS import_runs (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at  TEXT NOT NULL,
                    finished_at TEXT,
                    sources     TEXT,
                    total_fetched INTEGER DEFAULT 0,
                    total_posted  INTEGER DEFAULT 0,
                    status      TEXT DEFAULT 'running'
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_imported_source
                ON imported_posts(source)
            """)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def is_duplicate(self, post: NormalizedPost) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM imported_posts WHERE fingerprint = ?",
                (post.fingerprint,),
            ).fetchone()
            return row is not None

    def filter_new(self, posts: list[NormalizedPost]) -> list[NormalizedPost]:
        """Return only posts that haven't been imported before."""
        new = [p for p in posts if not self.is_duplicate(p)]
        logger.info("Dedup: %d / %d are new", len(new), len(posts))
        return new

    def mark_imported(
        self, post: NormalizedPost, lemmy_post_id: int | None = None
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO imported_posts
                   (fingerprint, url, title, source, lemmy_post_id, imported_at, ai_rank, ai_reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    post.fingerprint,
                    post.url,
                    post.title,
                    post.source,
                    lemmy_post_id,
                    datetime.now(timezone.utc).isoformat(),
                    post.ai_rank,
                    post.ai_reason,
                ),
            )

    # ── Run tracking ──────────────────────────────────────────────

    def start_run(self, sources: str) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO import_runs (started_at, sources) VALUES (?, ?)",
                (datetime.now(timezone.utc).isoformat(), sources),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def finish_run(
        self, run_id: int, total_fetched: int, total_posted: int, status: str = "ok"
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """UPDATE import_runs
                   SET finished_at=?, total_fetched=?, total_posted=?, status=?
                   WHERE id=?""",
                (
                    datetime.now(timezone.utc).isoformat(),
                    total_fetched,
                    total_posted,
                    status,
                    run_id,
                ),
            )

    def recent_imports(self, limit: int = 50) -> list[dict]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM imported_posts ORDER BY imported_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def recent_runs(self, limit: int = 20) -> list[dict]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM import_runs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def stats(self) -> dict:
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM imported_posts").fetchone()[0]
            by_source = conn.execute(
                "SELECT source, COUNT(*) as cnt FROM imported_posts GROUP BY source"
            ).fetchall()
            return {
                "total_imported": total,
                "by_source": {row[0]: row[1] for row in by_source},
            }
