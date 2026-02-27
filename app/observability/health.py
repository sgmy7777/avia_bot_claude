from __future__ import annotations

"""
Health-check модуль для Docker (fix #5).

Воркер периодически записывает временную метку в файл /tmp/avia_bot_health.
Docker HEALTHCHECK читает этот файл и проверяет, что он обновлялся недавно.

Добавить в Dockerfile:
    HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
        CMD python3 -c "
import os, time, sys
p='/tmp/avia_bot_health'
if not os.path.exists(p): sys.exit(1)
age = time.time() - os.path.getmtime(p)
sys.exit(0 if age < 900 else 1)  # fail если файл старше 15 минут
"
"""

import os
import time
import logging
from pathlib import Path
from threading import Thread

logger = logging.getLogger(__name__)

HEALTH_FILE = Path(os.getenv("HEALTH_FILE", "/tmp/avia_bot_health"))


def touch_health() -> None:
    """Обновляет временную метку health-файла."""
    try:
        HEALTH_FILE.write_text(str(time.time()))
    except Exception as exc:  # noqa: BLE001
        logger.warning("health touch failed: %s", exc)


def start_health_ticker(interval_seconds: int = 60) -> None:
    """
    Запускает фоновый поток, который обновляет health-файл каждые N секунд.
    Вызывать один раз при старте воркера.
    """
    def _tick() -> None:
        while True:
            touch_health()
            time.sleep(interval_seconds)

    thread = Thread(target=_tick, daemon=True, name="health-ticker")
    thread.start()
    logger.info("health ticker started | file=%s interval=%ds", HEALTH_FILE, interval_seconds)
