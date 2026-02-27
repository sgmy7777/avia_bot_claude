import pytest
from datetime import datetime, timedelta, timezone

pytest.importorskip("httpx")

from app.domain.models import Incident
from app.main import _is_recent_incident, _merge_with_details, _parse_incident_date


def test_merge_with_details_prefers_detail_values() -> None:
    incident = Incident(
        incident_id="i1",
        title="Old title",
        event_type="incident",
        date_utc="",
        location="",
        aircraft="",
        operator="",
        persons_onboard="",
        summary="short",
        source_url="https://x",
    )
    details = {
        "title": "New title",
        "date_utc": "2026-01-01",
        "location": "Cairo",
        "aircraft": "A320",
        "operator": "Air Test",
        "summary": "Long detailed text",
    }

    merged = _merge_with_details(incident, details)

    assert merged.title == "New title"
    assert merged.location == "Cairo"
    assert merged.summary == "Long detailed text"


def test_parse_incident_date_common_formats() -> None:
    assert _parse_incident_date("24 Feb 2026") is not None
    assert _parse_incident_date("Tue, 24 Feb 2026 10:00:00 GMT") is not None


def test_is_recent_incident_window_today_and_yesterday() -> None:
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    old = today - timedelta(days=3)

    i_today = Incident("1", "t", "incident", today.strftime("%d %b %Y"), "", "", "", "", "", "u")
    i_yday = Incident("2", "t", "incident", yesterday.strftime("%d %b %Y"), "", "", "", "", "", "u")
    i_old = Incident("3", "t", "incident", old.strftime("%d %b %Y"), "", "", "", "", "", "u")

    assert _is_recent_incident(i_today, 1) is True
    assert _is_recent_incident(i_yday, 1) is True
    assert _is_recent_incident(i_old, 1) is False
