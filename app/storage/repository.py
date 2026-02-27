from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.domain.models import Incident

# Максимальное число retry-попыток для failed-инцидентов (fix #2)
MAX_RETRY_ATTEMPTS = 3


class IncidentRepository:
    def __init__(self, database_url: str) -> None:
        if not database_url.startswith("sqlite:///"):
            raise ValueError("Only sqlite:/// URLs are supported in MVP")
        self._db_path = Path(database_url.removeprefix("sqlite:///"))
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
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
                """
            )
            # Миграция: добавляем колонки если их нет (для существующих БД)
            self._migrate_add_column(conn, "retry_count", "INTEGER NOT NULL DEFAULT 0")
            self._migrate_add_column(conn, "last_error", "TEXT")
            conn.commit()

    @staticmethod
    def _migrate_add_column(conn: sqlite3.Connection, column: str, definition: str) -> None:
        try:
            conn.execute(f"ALTER TABLE incidents ADD COLUMN {column} {definition}")
        except sqlite3.OperationalError:
            pass  # Колонка уже существует

    def exists(self, incident_id: str) -> bool:
        """
        Возвращает True если инцидент уже обработан И не требует retry.
        Failed-инциденты с retry_count < MAX_RETRY_ATTEMPTS считаются не обработанными. (fix #2)
        """
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT status, retry_count FROM incidents
                WHERE incident_id = ?
                LIMIT 1
                """,
                (incident_id,),
            )
            row = cur.fetchone()

        if row is None:
            return False

        status = row["status"]
        retry_count = row["retry_count"] or 0

        # Published и skipped — не трогаем
        if status in ("published", "skipped"):
            return True

        # Failed: разрешаем retry до MAX_RETRY_ATTEMPTS раз
        if status == "failed":
            return retry_count >= MAX_RETRY_ATTEMPTS

        # discovered — ещё не опубликован, обрабатываем
        return False

    def save_discovered(self, incident: Incident) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO incidents (
                    incident_id, title, date_utc, location, aircraft, source_url,
                    rewrite_text, status, first_seen_at, published_at, retry_count, last_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    incident.incident_id,
                    incident.title,
                    incident.date_utc,
                    incident.location,
                    incident.aircraft,
                    incident.source_url,
                    "",
                    "discovered",
                    datetime.now(timezone.utc).isoformat(),
                    None,
                    0,
                    None,
                ),
            )
            conn.commit()

    def mark_published(self, incident_id: str, rewrite_text: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE incidents
                SET rewrite_text = ?, status = ?, published_at = ?, last_error = NULL
                WHERE incident_id = ?
                """,
                (
                    rewrite_text,
                    "published",
                    datetime.now(timezone.utc).isoformat(),
                    incident_id,
                ),
            )
            conn.commit()

    def mark_skipped(self, incident_id: str, rewrite_text: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE incidents SET rewrite_text = ?, status = ? WHERE incident_id = ?",
                (rewrite_text, "skipped", incident_id),
            )
            conn.commit()

    def mark_failed(self, incident_id: str, error: str) -> None:
        """Увеличивает счётчик retry и сохраняет текст ошибки. (fix #2)"""
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE incidents
                SET status = 'failed',
                    retry_count = retry_count + 1,
                    last_error = ?
                WHERE incident_id = ?
                """,
                (error, incident_id),
            )
            conn.commit()

    def reset_dry_run_skipped(self) -> int:
        """
        Сбрасывает статус 'skipped' для dry-run записей,
        чтобы они были переопубликованы при следующем реальном запуске. (fix #10)

        Возвращает число сброшенных записей.
        """
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE incidents
                SET status = 'discovered', rewrite_text = ''
                WHERE status = 'skipped' AND rewrite_text = 'dry_run_skip_publish'
                """
            )
            conn.commit()
            return cur.rowcount

    def get_stats(self) -> dict[str, int]:
        """Возвращает сводную статистику по статусам."""
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM incidents GROUP BY status"
            )
            return {row["status"]: row["cnt"] for row in cur.fetchall()}
