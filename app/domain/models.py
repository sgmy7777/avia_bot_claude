from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Incident:
    incident_id: str
    title: str
    event_type: str
    date_utc: str
    location: str
    aircraft: str
    operator: str
    persons_onboard: str
    summary: str
    source_url: str


@dataclass(frozen=True)
class RewriteInput:
    incident: Incident
