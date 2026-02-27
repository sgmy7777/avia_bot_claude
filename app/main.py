from __future__ import annotations

import argparse
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from app.ai.deepseek_client import DeepSeekClient
from app.ai.validator import validate_fallback, validate_rewrite
from app.bootstrap import load_dotenv
from app.collector.aviation_safety import AviationSafetyCollector
from app.config import Settings
from app.domain.models import Incident
from app.domain.normalizer import normalize_incident
from app.observability.health import start_health_ticker, touch_health
from app.observability.logging import setup_logging
from app.publisher.telegram_client import TelegramPublisher
from app.storage.repository import IncidentRepository

logger = logging.getLogger("avia_bot")

# Задержка между HTTP-запросами к ASN для избежания блокировки (fix #3)
ASN_REQUEST_DELAY_SECONDS = 1.5

# Порог числа подряд идущих ошибок для отправки алерта (fix #8)
ALERT_CONSECUTIVE_FAILURES_THRESHOLD = 3


@dataclass
class CycleStats:
    """Статистика одного цикла обработки (fix #9)."""
    fetched: int = 0
    new: int = 0
    published: int = 0
    skipped_dedup: int = 0
    skipped_date: int = 0
    skipped_dry_run: int = 0
    failed: int = 0
    consecutive_failures: int = 0

    def summary(self) -> str:
        return (
            f"fetched={self.fetched} | new={self.new} | published={self.published} | "
            f"skipped_dedup={self.skipped_dedup} | skipped_date={self.skipped_date} | "
            f"skipped_dry_run={self.skipped_dry_run} | failed={self.failed}"
        )


def _merge_with_details(incident: Incident, details: dict[str, str]) -> Incident:
    if not details:
        return incident

    return Incident(
        incident_id=incident.incident_id,
        title=details.get("title") or incident.title,
        event_type=incident.event_type,
        date_utc=details.get("date_utc") or incident.date_utc,
        location=details.get("location") or incident.location,
        aircraft=details.get("aircraft") or incident.aircraft,
        operator=details.get("operator") or incident.operator,
        persons_onboard=incident.persons_onboard,
        summary=details.get("summary") or incident.summary,
        source_url=incident.source_url,
    )


def _normalize_date_string(text: str) -> str:
    """
    Нормализует строку даты перед парсингом.
    Заменяет 'GMT' на '+0000' для корректной кросс-платформенной обработки (fix #7).
    """
    return text.replace(" GMT", " +0000").strip()


def _parse_incident_date(value: str) -> date | None:
    text = _normalize_date_string(value or "")
    if not text:
        return None

    formats = [
        "%d %b %Y",
        "%d %B %Y",
        "%Y-%m-%d",
        "%a, %d %b %Y %H:%M:%S %z",   # RFC 2822 с +0000 (fix #7)
        "%a, %d %b %Y %H:%M:%S GMT",  # fallback на случай если нормализация не сработала
    ]
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    # Fallback: извлечь подстроку вида '24 Feb 2026'
    m = re.search(r"(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})", text)
    if m:
        for fmt in ("%d %b %Y", "%d %B %Y"):
            try:
                return datetime.strptime(m.group(1), fmt).date()
            except ValueError:
                pass

    return None


def _is_recent_incident(incident: Incident, days_back: int) -> bool:
    return _is_recent_date_value(incident.date_utc, days_back)


def _is_recent_date_value(date_value: str, days_back: int) -> bool:
    incident_day = _parse_incident_date(date_value)
    if incident_day is None:
        return True

    today = datetime.now(timezone.utc).date()
    earliest = today - timedelta(days=days_back)
    return earliest <= incident_day <= today


def _build_rewriter(settings: Settings) -> DeepSeekClient:
    provider_mode = settings.llm_provider

    if provider_mode == "auto":
        provider_mode = "openrouter" if settings.openrouter_api_key else "deepseek"

    if provider_mode == "openrouter":
        api_key = settings.openrouter_api_key
        model = settings.openrouter_model
        base_url = settings.openrouter_base_url
        extra_headers = {
            "HTTP-Referer": settings.openrouter_site_url,
            "X-Title": settings.openrouter_app_name,
        }
        provider_name = "openrouter"
        if not api_key:
            logger.warning("LLM_PROVIDER=openrouter, но OPENROUTER_API_KEY пуст. Будет использован fallback-рерайт.")
    else:
        api_key = settings.deepseek_api_key
        model = settings.deepseek_model
        base_url = settings.deepseek_base_url
        extra_headers = {}
        provider_name = "deepseek"

    logger.info(
        "LLM provider mode: %s -> active: %s | model: %s | base_url: %s",
        settings.llm_provider,
        provider_name,
        model,
        base_url,
    )

    return DeepSeekClient(
        api_key=api_key,
        model=model,
        base_url=base_url,
        provider_name=provider_name,
        extra_headers=extra_headers,
    )


def process_once(settings: Settings) -> CycleStats:
    collector = AviationSafetyCollector(settings.user_agent, settings.asn_feed_urls)
    repository = IncidentRepository(settings.database_url)
    rewriter = _build_rewriter(settings)
    publisher = TelegramPublisher(
        settings.telegram_bot_token,
        settings.telegram_channel,
        alert_chat_id=settings.telegram_alert_chat_id,  # fix #8
    )

    stats = CycleStats()

    raw_items = collector.fetch_recent_incidents()
    stats.fetched = len(raw_items)
    logger.info("fetched %d candidate incidents", stats.fetched)

    for raw in raw_items:
        if stats.published >= settings.max_publications_per_cycle:
            logger.info("publication limit reached for cycle: %d", settings.max_publications_per_cycle)
            break

        incident = normalize_incident(raw)

        if repository.exists(incident.incident_id):
            stats.skipped_dedup += 1
            continue

        # Быстрый pre-filter по дате из списка (без загрузки детальной страницы)
        if incident.date_utc and not _is_recent_date_value(incident.date_utc, settings.date_window_days):
            logger.info(
                "skip by list date | id=%s date=%s",
                incident.incident_id,
                incident.date_utc,
            )
            stats.skipped_date += 1
            continue

        # Rate limiting между запросами к ASN (fix #3)
        time.sleep(ASN_REQUEST_DELAY_SECONDS)

        details = collector.fetch_incident_details(incident.source_url)
        incident = _merge_with_details(incident, details)

        if not _is_recent_incident(incident, settings.date_window_days):
            logger.info(
                "skip by detail date | id=%s date=%s",
                incident.incident_id,
                incident.date_utc,
            )
            stats.skipped_date += 1
            continue

        stats.new += 1
        repository.save_discovered(incident)

        try:
            rewritten = rewriter.rewrite_incident(incident)

            # Определяем, был ли использован fallback (fix #6)
            is_fallback = not rewriter.is_api_rewrite_available()
            validator_fn = validate_fallback if is_fallback else validate_rewrite
            valid, reason = validator_fn(rewritten)

            if not valid:
                logger.warning(
                    "rewrite validation failed | id=%s reason=%s fallback=%s",
                    incident.incident_id,
                    reason,
                    is_fallback,
                )

            # DRY_RUN: обрабатываем без публикации.
            # ВНИМАНИЕ: incident_id сохраняется в БД со статусом 'skipped'.
            # При следующем запуске без DRY_RUN этот инцидент НЕ будет опубликован,
            # так как exists() вернёт True.
            # Для сброса используйте --dry-run-reset или удалите запись из БД вручную. (fix #10)
            if settings.dry_run:
                logger.info("DRY_RUN=true, skip publish | id=%s", incident.incident_id)
                repository.mark_skipped(incident.incident_id, "dry_run_skip_publish")
                stats.skipped_dry_run += 1
                continue

            publisher.publish(rewritten)
            repository.mark_published(incident.incident_id, rewritten)
            stats.published += 1
            stats.consecutive_failures = 0
            logger.info("published | id=%s", incident.incident_id)

        except Exception as exc:  # noqa: BLE001
            logger.exception("failed to process incident | id=%s error=%s", incident.incident_id, exc)
            repository.mark_failed(incident.incident_id, str(exc))
            stats.failed += 1
            stats.consecutive_failures += 1

            # Алерт при серии ошибок (fix #8)
            if stats.consecutive_failures >= ALERT_CONSECUTIVE_FAILURES_THRESHOLD:
                publisher.send_alert(
                    f"⚠️ {stats.consecutive_failures} подряд идущих ошибок публикации.\n"
                    f"Последняя: `{exc}`"
                )

    # Итоговая статистика цикла (fix #9)
    logger.info("cycle complete | %s", stats.summary())

    return stats


def send_test_message(settings: Settings) -> None:
    publisher = TelegramPublisher(settings.telegram_bot_token, settings.telegram_channel)
    text = (
        "✅ Тестовое сообщение avia\\_bot\n\n"
        "Интеграция Telegram настроена корректно."
    )
    publisher.publish(text)
    logger.info("test message sent to %s", settings.telegram_channel)


def run_forever(settings: Settings) -> None:
    logger.info("starting worker | interval=%s min", settings.poll_interval_minutes)
    consecutive_cycle_failures = 0

    start_health_ticker()  # fix #5: health check для Docker

    publisher = TelegramPublisher(
        settings.telegram_bot_token,
        settings.telegram_channel,
        alert_chat_id=settings.telegram_alert_chat_id,
    )

    while True:
        try:
            process_once(settings)
            consecutive_cycle_failures = 0
            touch_health()  # fix #5: обновляем health-файл после успешного цикла
        except Exception as exc:  # noqa: BLE001
            consecutive_cycle_failures += 1
            logger.exception("worker cycle failed | error=%s consecutive=%d", exc, consecutive_cycle_failures)

            # Алерт если весь цикл падает подряд (fix #8)
            if consecutive_cycle_failures >= ALERT_CONSECUTIVE_FAILURES_THRESHOLD:
                publisher.send_alert(
                    f"❌ Цикл воркера упал {consecutive_cycle_failures} раз подряд.\n"
                    f"Последняя ошибка: `{exc}`"
                )

        time.sleep(settings.poll_interval_minutes * 60)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ASN -> Telegram monitoring bot")
    parser.add_argument("--once", action="store_true", help="process incidents once and exit")
    parser.add_argument(
        "--test-telegram",
        action="store_true",
        help="send one test message to Telegram channel and exit",
    )
    parser.add_argument(
        "--dry-run-reset",
        action="store_true",
        help=(
            "сбросить статус 'skipped' для всех dry-run записей, "
            "чтобы они были переопубликованы при следующем запуске без DRY_RUN"
        ),
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()
    settings = Settings.from_env()

    # Настраиваем логирование через observability-модуль (fix #4)
    setup_logging(
        level=settings.log_level,
        json_logs=settings.json_logs,
    )

    if args.test_telegram:
        send_test_message(settings)
        return

    if args.dry_run_reset:
        repository = IncidentRepository(settings.database_url)
        count = repository.reset_dry_run_skipped()
        logger.info("dry-run reset complete | reset_count=%d", count)
        return

    if args.once:
        try:
            process_once(settings)
        except Exception as exc:  # noqa: BLE001
            logger.error("one-shot run failed | error=%s", exc)
        return

    run_forever(settings)


if __name__ == "__main__":
    main()
