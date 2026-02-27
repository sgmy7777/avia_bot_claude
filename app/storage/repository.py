from __future__ import annotations

"""
Repository с поддержкой SQLite (локально) и PostgreSQL (Railway/prod).

DATABASE_URL форматы:
  sqlite:///./data/avia.db          — локально
  postgresql://user:pass@host/db    — Railway PostgreSQL
  postgres://user:pass@host/db      — Railway (алиас, автоматически нормализуется)
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

from app.domain.models import Incident

MAX_RETRY_ATTEMPTS = 3


class IncidentRepository:
    def __init__(self, database_url: str) -> None:
        # Railway иногда отдаёт postgres:// — нормализуем
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)

        self._url = database_url
        self._is_pg = database_url.startswith("postgresql://")

        if self._is_pg:
            self._init_pg()
        else:
            self._init_sqlite()

        self._ensure_schema()

    def _init_pg(self) -> None:
        try:
            import psycopg2  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "psycopg2 не установлен. Добавьте 'psycopg2-binary' в requirements.txt"
            ) from exc
        self._pg_url = self._url

    def _init_sqlite(self) -> None:
        if not self._url.startswith("sqlite:///"):
            raise ValueError(f"Неподдерживаемый DATABASE_URL: {self._url}")
        self._db_path = Path(self._url.removeprefix("sqlite:///"))
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _conn(self) -> Generator[Any, None, None]:
        if self._is_pg:
            import psycopg2
            conn = psycopg2.connect(self._pg_url)
            conn.autocommit = False
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
        else:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def _ph(self) -> str:
        return "%s" if self._is_pg else "?"

    def _fetchone(self, cursor: Any) -> dict | None:
        row = cursor.fetchone()
        if row is None:
            return None
        if self._is_pg:
            cols = [desc[0] for desc in cursor.description]
            return dict(zip(cols, row))
        return dict(row)

    def _fetchall(self, cursor: Any) -> list[dict]:
        rows = cursor.fetchall()
        if self._is_pg:
            cols = [desc[0] for desc in cursor.description]
            return [dict(zip(cols, r)) for r in rows]
        return [dict(r) for r in rows]

    def _ensure_schema(self) -> None:
        ph = self._ph()
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS incidents (
                    incident_id     TEXT    PRIMARY KEY,
                    title           TEXT    NOT NULL,
                    date_utc        TEXT,
                    location        TEXT,
                    aircraft        TEXT,
                    source_url      TEXT,
                    rewrite_text    TEXT,
                    status          TEXT    NOT NULL,
                    first_seen_at   TEXT    NOT NULL,
                    published_at    TEXT,
                    retry_count     INTEGER NOT NULL DEFAULT 0,
                    last_error      TEXT
                )
            """)
            if not self._is_pg:
                for col, definition in [
                    ("retry_count", "INTEGER NOT NULL DEFAULT 0"),
                    ("last_error", "TEXT"),
                ]:
                    try:
                        cur.execute(f"ALTER TABLE incidents ADD COLUMN {col} {definition}")
                    except sqlite3.OperationalError:
                        pass

    def exists(self, incident_id: str) -> bool:
        ph = self._ph()
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                f"SELECT status, retry_count FROM incidents WHERE incident_id = {ph} LIMIT 1",
                (incident_id,),
            )
            row = self._fetchone(cur)

        if row is None:
            return False
        status = row["status"]
        retry_count = row.get("retry_count") or 0
        if status in ("published", "skipped"):
            return True
        if status == "failed":
            return retry_count >= MAX_RETRY_ATTEMPTS
        return False

    def save_discovered(self, incident: Incident) -> None:
        ph = self._ph()
        conflict = "ON CONFLICT (incident_id) DO NOTHING" if self._is_pg else ""
        or_ignore = "" if self._is_pg else "OR IGNORE"
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                f"""INSERT {or_ignore} INTO incidents (
                        incident_id, title, date_utc, location, aircraft, source_url,
                        rewrite_text, status, first_seen_at, published_at, retry_count, last_error
                    ) VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})
                    {conflict}""",
                (
                    incident.incident_id, incident.title, incident.date_utc,
                    incident.location, incident.aircraft, incident.source_url,
                    "", "discovered", datetime.now(timezone.utc).isoformat(),
                    None, 0, None,
                ),
            )

    def mark_published(self, incident_id: str, rewrite_text: str) -> None:
        ph = self._ph()
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                f"""UPDATE incidents
                    SET rewrite_text = {ph}, status = {ph}, published_at = {ph}, last_error = NULL
                    WHERE incident_id = {ph}""",
                (rewrite_text, "published", datetime.now(timezone.utc).isoformat(), incident_id),
            )

    def mark_skipped(self, incident_id: str, rewrite_text: str) -> None:
        ph = self._ph()
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                f"UPDATE incidents SET rewrite_text = {ph}, status = {ph} WHERE incident_id = {ph}",
                (rewrite_text, "skipped", incident_id),
            )

    def mark_failed(self, incident_id: str, error: str) -> None:
        ph = self._ph()
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                f"""UPDATE incidents
                    SET status = 'failed', retry_count = retry_count + 1, last_error = {ph}
                    WHERE incident_id = {ph}""",
                (error, incident_id),
            )

    def reset_dry_run_skipped(self) -> int:
        ph = self._ph()
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                f"""UPDATE incidents SET status = 'discovered', rewrite_text = ''
                    WHERE status = 'skipped' AND rewrite_text = {ph}""",
                ("dry_run_skip_publish",),
            )
            return cur.rowcount

    def get_stats(self) -> dict[str, int]:
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT status, COUNT(*) as cnt FROM incidents GROUP BY status")
            return {r["status"]: r["cnt"] for r in self._fetchall(cur)}
