from __future__ import annotations

import hashlib
from typing import Any

from app.domain.models import Incident


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def build_incident_id(date_utc: str, aircraft: str, location: str, source_url: str) -> str:
    """
    Если есть source_url — хэшируем только его (стабильный идентификатор).
    Это критично для RSS-инцидентов, где date/aircraft/location могут быть пустыми,
    что приводило к разным хэшам для одного и того же события.
    """
    if source_url:
        return hashlib.sha256(source_url.encode("utf-8")).hexdigest()[:24]
    payload = "|".join([date_utc, aircraft, location])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def normalize_incident(raw: dict[str, Any]) -> Incident:
    date_utc = _safe_text(raw.get("date_utc"))
    aircraft = _safe_text(raw.get("aircraft"))
    location = _safe_text(raw.get("location"))
    source_url = _safe_text(raw.get("source_url"))
    incident_id = build_incident_id(date_utc, aircraft, location, source_url)

    return Incident(
        incident_id=incident_id,
        title=_safe_text(raw.get("title")),
        event_type=_safe_text(raw.get("event_type")),
        date_utc=date_utc,
        location=location,
        aircraft=aircraft,
        operator=_safe_text(raw.get("operator")),
        persons_onboard=_safe_text(raw.get("persons_onboard")),
        summary=_safe_text(raw.get("summary")),
        source_url=source_url,
    )
