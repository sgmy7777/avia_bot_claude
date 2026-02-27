from app.domain.normalizer import build_incident_id, normalize_incident


def test_build_incident_id_uses_source_url_when_available() -> None:
    """fix #1: дедупликация по source_url стабильна даже при пустых полях."""
    url = "https://aviation-safety.net/database/record.php?id=20260115-0"

    id1 = build_incident_id("", "", "", url)
    id2 = build_incident_id("2026-01-15", "Airbus A320", "Cairo", url)

    assert id1 == id2, "incident_id должен быть одинаковым при одинаковом source_url"


def test_build_incident_id_without_source_url_uses_fields() -> None:
    """Без source_url хэшируем по дате+aircraft+location."""
    id1 = build_incident_id("2026-01-15", "Airbus A320", "Cairo", "")
    id2 = build_incident_id("2026-01-15", "Airbus A320", "Cairo", "")
    id3 = build_incident_id("2026-01-16", "Airbus A320", "Cairo", "")

    assert id1 == id2
    assert id1 != id3


def test_rss_incident_stable_id_across_cycles() -> None:
    """RSS-инциденты (без aircraft/location) должны иметь стабильный ID."""
    raw = {
        "title": "Airbus A320 incident near Cairo",
        "event_type": "incident",
        "date_utc": "Sat, 15 Jan 2026 12:00:00 GMT",
        "location": "",      # пусто в RSS
        "aircraft": "",      # пусто в RSS
        "source_url": "https://aviation-safety.net/database/record.php?id=20260115-0",
    }

    inc1 = normalize_incident(raw)
    inc2 = normalize_incident(raw)

    assert inc1.incident_id == inc2.incident_id
