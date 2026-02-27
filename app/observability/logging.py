from __future__ import annotations

import json
import logging
import os
import traceback
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """
    Форматирует логи в JSON для удобного парсинга в Grafana/ELK/Loki.

    Пример вывода:
    {"ts":"2026-02-25T10:00:00Z","level":"INFO","logger":"avia_bot","msg":"published incident","incident_id":"abc123"}
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        # Добавляем extra-поля, переданные через logging.info(..., extra={...})
        skip_fields = {
            "name", "msg", "args", "levelname", "levelno", "pathname",
            "filename", "module", "exc_info", "exc_text", "stack_info",
            "lineno", "funcName", "created", "msecs", "relativeCreated",
            "thread", "threadName", "processName", "process", "message",
            "taskName",
        }
        for key, val in record.__dict__.items():
            if key not in skip_fields and not key.startswith("_"):
                payload[key] = val

        if record.exc_info:
            payload["traceback"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str = "INFO", json_logs: bool | None = None) -> None:
    """
    Настраивает логирование.

    Args:
        level: уровень логирования (INFO, DEBUG, WARNING, ERROR)
        json_logs: True = JSON-формат, False = plain text.
                   None = авто (JSON если LOG_FORMAT=json или не TTY)
    """
    if json_logs is None:
        log_format = os.getenv("LOG_FORMAT", "").lower()
        json_logs = log_format == "json" or not os.isatty(1)

    handler = logging.StreamHandler()

    if json_logs:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Убираем дефолтные хендлеры, чтобы не было дублей
    root.handlers.clear()
    root.addHandler(handler)
