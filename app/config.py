from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone


def _parse_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_csv(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    items = [part.strip() for part in raw.split(",")]
    return [item for item in items if item]


def _default_asn_feed_urls() -> str:
    year = datetime.now(timezone.utc).year
    return (
        "https://aviation-safety.net/rss.xml,"
        f"https://aviation-safety.net/asndb/year/{year},"
        "https://aviation-safety.net/database/,"
        "https://aviation-safety.net/wikibase/dblist.php?Country="
    )


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_channel: str
    telegram_alert_chat_id: str      # fix #8: служебный чат для алертов
    deepseek_api_key: str
    deepseek_model: str
    deepseek_base_url: str
    llm_provider: str
    openrouter_api_key: str
    openrouter_model: str
    openrouter_base_url: str
    openrouter_site_url: str
    openrouter_app_name: str
    database_url: str
    poll_interval_minutes: int
    user_agent: str
    dry_run: bool
    asn_feed_urls: list[str]
    max_publications_per_cycle: int
    date_window_days: int
    log_level: str                   # fix #4: уровень логирования
    json_logs: bool                  # fix #4: JSON-формат логов

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            telegram_channel=os.getenv("TELEGRAM_CHANNEL", "@avia_crash"),
            telegram_alert_chat_id=os.getenv("TELEGRAM_ALERT_CHAT_ID", ""),  # fix #8
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
            llm_provider=os.getenv("LLM_PROVIDER", "auto").strip().lower(),
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY", ""),
            openrouter_model=os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat"),
            openrouter_base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            openrouter_site_url=os.getenv("OPENROUTER_SITE_URL", "https://github.com/sgmy7777/avia_bot"),
            openrouter_app_name=os.getenv("OPENROUTER_APP_NAME", "avia_bot"),
            database_url=os.getenv("DATABASE_URL", "sqlite:///./data/avia.db"),
            poll_interval_minutes=int(os.getenv("POLL_INTERVAL_MINUTES", "10")),
            user_agent=os.getenv(
                "USER_AGENT",
                "avia-bot/1.0 (+https://github.com/example/avia_bot)",
            ),
            dry_run=_parse_bool("DRY_RUN", False),
            asn_feed_urls=_parse_csv("ASN_FEED_URLS", _default_asn_feed_urls()),
            max_publications_per_cycle=int(os.getenv("MAX_PUBLICATIONS_PER_CYCLE", "10")),
            date_window_days=int(os.getenv("DATE_WINDOW_DAYS", "1")),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),               # fix #4
            json_logs=_parse_bool("LOG_FORMAT_JSON", False),                # fix #4
        )
