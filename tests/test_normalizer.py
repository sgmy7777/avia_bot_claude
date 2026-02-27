from app.domain.normalizer import normalize_incident


def test_normalize_incident_builds_stable_id() -> None:
    raw = {
        "title": "Engine issue after takeoff",
        "event_type": "incident",
        "date_utc": "2026-01-15",
        "location": "Cairo",
        "aircraft": "Airbus A320-200",
        "source_url": "https://aviation-safety.net/example",
    }
    incident = normalize_incident(raw)

    assert incident.incident_id
    assert incident.aircraft == "Airbus A320-200"
    assert incident.location == "Cairo"
