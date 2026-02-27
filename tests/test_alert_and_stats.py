import httpx
import pytest

from app.publisher.telegram_client import TelegramPublisher


class _MockResponse:
    def __init__(self, status_code: int, json_data: dict | None = None) -> None:
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = ""

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> dict:
        return self._json_data


class _MockClient:
    def __init__(self, responses: list[_MockResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    def __enter__(self) -> "_MockClient":
        return self

    def __exit__(self, *args) -> None:
        pass

    def post(self, url: str, json: dict) -> _MockResponse:
        self.calls.append({"url": url, "json": json})
        return self._responses.pop(0)


def test_send_alert_sends_to_alert_chat(monkeypatch) -> None:
    """fix #8: алерт отправляется в alert_chat_id, а не в основной канал."""
    mock = _MockClient([_MockResponse(200, {"ok": True})])
    monkeypatch.setattr(httpx, "Client", lambda timeout: mock)

    publisher = TelegramPublisher("token", "@avia_crash", alert_chat_id="@avia_admin")
    publisher.send_alert("Something went wrong")

    assert len(mock.calls) == 1
    assert mock.calls[0]["json"]["chat_id"] == "@avia_admin"
    assert "ALERT" in mock.calls[0]["json"]["text"]
    assert "Something went wrong" in mock.calls[0]["json"]["text"]


def test_send_alert_logs_when_no_chat_configured(caplog) -> None:
    """fix #8: без alert_chat_id — только лог, без HTTP-запроса."""
    import logging
    publisher = TelegramPublisher("token", "@avia_crash", alert_chat_id="")

    with caplog.at_level(logging.WARNING):
        publisher.send_alert("test alert")

    assert "ALERT" in caplog.text
    assert "test alert" in caplog.text


def test_cycle_stats_summary_format() -> None:
    """fix #9: сводка статистики содержит все ключевые поля."""
    from app.main import CycleStats

    stats = CycleStats(
        fetched=42,
        new=5,
        published=3,
        skipped_dedup=35,
        skipped_date=2,
        skipped_dry_run=0,
        failed=2,
    )
    summary = stats.summary()

    assert "fetched=42" in summary
    assert "new=5" in summary
    assert "published=3" in summary
    assert "skipped_dedup=35" in summary
    assert "skipped_date=2" in summary
    assert "failed=2" in summary
