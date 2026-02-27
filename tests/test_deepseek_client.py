import pytest

httpx = pytest.importorskip("httpx")

from app.ai.deepseek_client import DeepSeekClient
from app.domain.models import Incident


class _DummyResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                message=f"status={self.status_code}",
                request=httpx.Request("POST", "https://api.deepseek.com/v1/chat/completions"),
                response=httpx.Response(self.status_code),
            )

    def json(self) -> dict:
        return self._payload


class _DummyClient:
    def __init__(self, response: _DummyResponse) -> None:
        self._response = response
        self.last_url = ""
        self.calls = 0
        self.last_headers: dict = {}

    def __enter__(self) -> "_DummyClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def post(self, url: str, headers: dict, json: dict) -> _DummyResponse:  # noqa: A002
        self.last_url = url
        self.calls += 1
        self.last_headers = headers
        return self._response


def _incident() -> Incident:
    return Incident(
        incident_id="abc",
        title="Test incident",
        event_type="incident",
        date_utc="2026-01-01",
        location="Cairo",
        aircraft="Airbus A320",
        operator="Air Test",
        persons_onboard="150",
        summary="Engine issue",
        source_url="https://aviation-safety.net/database/record.php?id=1",
    )


def test_rewrite_uses_fallback_on_402(monkeypatch) -> None:
    client_mock = _DummyClient(_DummyResponse(402, payload={"error": "insufficient_balance"}))
    monkeypatch.setattr(httpx, "Client", lambda timeout: client_mock)
    client = DeepSeekClient("key", "deepseek-chat", "https://api.deepseek.com/v1")

    text = client.rewrite_incident(_incident())

    assert "Источник:" not in text
    assert "#авиация #происшествие #небонаграни #авиабезопасность" in text
    assert "✈️" in text
    assert "📍" in text


def test_rewrite_disables_deepseek_after_first_402(monkeypatch) -> None:
    client_mock = _DummyClient(_DummyResponse(402, payload={"error": "insufficient_balance"}))
    monkeypatch.setattr(httpx, "Client", lambda timeout: client_mock)
    client = DeepSeekClient("key", "deepseek-chat", "https://api.deepseek.com/v1")

    client.rewrite_incident(_incident())
    client.rewrite_incident(_incident())

    assert client_mock.calls == 1


def test_rewrite_uses_api_when_success(monkeypatch) -> None:
    payload = {"choices": [{"message": {"content": "ok rewrite"}}]}
    client_mock = _DummyClient(_DummyResponse(200, payload))
    monkeypatch.setattr(httpx, "Client", lambda timeout: client_mock)
    client = DeepSeekClient("key", "deepseek-chat", "https://api.deepseek.com/v1")

    text = client.rewrite_incident(_incident())

    assert text == "ok rewrite"
    assert client_mock.last_url == "https://api.deepseek.com/v1/chat/completions"


def test_rewrite_sends_openrouter_headers(monkeypatch) -> None:
    payload = {"choices": [{"message": {"content": "ok rewrite"}}]}
    client_mock = _DummyClient(_DummyResponse(200, payload))
    monkeypatch.setattr(httpx, "Client", lambda timeout: client_mock)
    client = DeepSeekClient(
        "key",
        "deepseek/deepseek-chat",
        "https://openrouter.ai/api/v1",
        provider_name="openrouter",
        extra_headers={"HTTP-Referer": "https://example.com", "X-Title": "avia_bot"},
    )

    client.rewrite_incident(_incident())

    assert client_mock.last_headers["HTTP-Referer"] == "https://example.com"
    assert client_mock.last_headers["X-Title"] == "avia_bot"
