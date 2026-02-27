import httpx

from app.publisher.telegram_client import TelegramPublisher


class _DummyResponse:
    def __init__(self, status_code: int, json_data: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> dict:
        if self._json_data is None:
            raise ValueError("no json")
        return self._json_data


class _DummyClient:
    def __init__(self, responses: list[_DummyResponse]) -> None:
        self._responses = responses
        self.calls: list[dict] = []

    def __enter__(self) -> "_DummyClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def post(self, url: str, json: dict) -> _DummyResponse:  # noqa: A002
        self.calls.append(json)
        return self._responses.pop(0)


def test_publish_raises_clear_error(monkeypatch) -> None:
    client = _DummyClient(
        [_DummyResponse(400, json_data={"ok": False, "description": "Bad Request: chat not found"})]
    )
    monkeypatch.setattr(httpx, "Client", lambda timeout: client)

    publisher = TelegramPublisher("token", "@bad_channel")

    try:
        publisher.publish("test")
        assert False, "Expected RuntimeError"
    except RuntimeError as exc:
        message = str(exc)

    assert "status=400" in message
    assert "chat not found" in message


def test_publish_retries_without_parse_mode_on_entities_error(monkeypatch) -> None:
    client = _DummyClient(
        [
            _DummyResponse(
                400,
                json_data={
                    "ok": False,
                    "description": "Bad Request: can't parse entities: Can't find end of the entity",
                },
            ),
            _DummyResponse(200, json_data={"ok": True}),
        ]
    )
    monkeypatch.setattr(httpx, "Client", lambda timeout: client)

    publisher = TelegramPublisher("token", "@avia_crash")
    publisher.publish("✅ Тестовое сообщение avia_bot")

    assert len(client.calls) == 2
    assert client.calls[0].get("parse_mode") == "Markdown"
    assert "parse_mode" not in client.calls[1]


def test_publish_requires_channel() -> None:
    publisher = TelegramPublisher("token", "")

    try:
        publisher.publish("test")
        assert False, "Expected RuntimeError"
    except RuntimeError as exc:
        assert "TELEGRAM_CHANNEL is empty" in str(exc)
