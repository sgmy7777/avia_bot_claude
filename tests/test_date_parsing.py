from datetime import date

import pytest

from app.main import _parse_incident_date, _is_recent_date_value


@pytest.mark.parametrize("raw, expected_date", [
    # Стандартные форматы ASN
    ("15 Jan 2026",                         date(2026, 1, 15)),
    ("15 January 2026",                     date(2026, 1, 15)),
    ("2026-01-15",                          date(2026, 1, 15)),
    # RSS RFC 2822 — основные случаи (fix #7, #11)
    ("Sat, 15 Jan 2026 12:00:00 GMT",       date(2026, 1, 15)),
    ("Thu, 24 Feb 2026 10:00:00 GMT",       date(2026, 2, 24)),
    ("Mon, 01 Jan 2026 00:00:00 GMT",       date(2026, 1, 1)),
    # Вариант с +0000
    ("Sat, 15 Jan 2026 12:00:00 +0000",     date(2026, 1, 15)),
    # Fallback regex
    ("Published: 15 Jan 2026 at 12:00",    date(2026, 1, 15)),
])
def test_parse_incident_date_formats(raw: str, expected_date: date) -> None:
    """fix #7, #11: проверяем все форматы включая GMT из RSS."""
    result = _parse_incident_date(raw)
    assert result == expected_date, f"Failed for: {raw!r} -> got {result}"


def test_parse_incident_date_empty_returns_none() -> None:
    assert _parse_incident_date("") is None
    assert _parse_incident_date("   ") is None


def test_parse_incident_date_unknown_format_returns_none() -> None:
    assert _parse_incident_date("не дата") is None


def test_is_recent_date_value_rss_gmt(monkeypatch) -> None:
    """fix #7: RSS-дата с GMT не должна блокировать публикацию."""
    # Используем дату которая точно в пределах окна (2 дня)
    from datetime import datetime, timezone, timedelta
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    rss_date = yesterday.strftime("%a, %d %b %Y 10:00:00 GMT")

    assert _is_recent_date_value(rss_date, days_back=1) is True
