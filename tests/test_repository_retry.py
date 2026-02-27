import pytest
from app.domain.models import Incident
from app.storage.repository import IncidentRepository, MAX_RETRY_ATTEMPTS


def _make_incident(incident_id: str = "test_id_001") -> Incident:
    return Incident(
        incident_id=incident_id,
        title="Test",
        event_type="incident",
        date_utc="2026-01-15",
        location="Cairo",
        aircraft="A320",
        operator="Air Test",
        persons_onboard="150",
        summary="Engine issue",
        source_url="https://aviation-safety.net/db/test",
    )


@pytest.fixture
def repo(tmp_path) -> IncidentRepository:
    return IncidentRepository(f"sqlite:///{tmp_path}/test.db")


def test_failed_incident_retried_up_to_max(repo: IncidentRepository) -> None:
    """fix #2: failed-инцидент должен ретраиться до MAX_RETRY_ATTEMPTS раз."""
    inc = _make_incident()
    repo.save_discovered(inc)

    for attempt in range(MAX_RETRY_ATTEMPTS):
        assert repo.exists(inc.incident_id) is False, f"Должен ретраиться на попытке {attempt + 1}"
        repo.mark_failed(inc.incident_id, "some error")

    # После MAX_RETRY_ATTEMPTS exists() возвращает True
    assert repo.exists(inc.incident_id) is True


def test_published_incident_not_retried(repo: IncidentRepository) -> None:
    inc = _make_incident()
    repo.save_discovered(inc)
    repo.mark_published(inc.incident_id, "text")

    assert repo.exists(inc.incident_id) is True


def test_dry_run_reset_unblocks_incidents(repo: IncidentRepository) -> None:
    """fix #10: --dry-run-reset позволяет переопубликовать dry-run записи."""
    inc = _make_incident()
    repo.save_discovered(inc)
    repo.mark_skipped(inc.incident_id, "dry_run_skip_publish")

    assert repo.exists(inc.incident_id) is True

    count = repo.reset_dry_run_skipped()
    assert count == 1
    assert repo.exists(inc.incident_id) is False


def test_dry_run_reset_does_not_touch_other_skipped(repo: IncidentRepository) -> None:
    """Обычный skipped (не dry-run) не должен сбрасываться."""
    inc = _make_incident()
    repo.save_discovered(inc)
    repo.mark_skipped(inc.incident_id, "some_other_reason")

    count = repo.reset_dry_run_skipped()
    assert count == 0
    assert repo.exists(inc.incident_id) is True
