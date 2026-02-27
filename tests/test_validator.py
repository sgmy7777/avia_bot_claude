from app.ai.validator import validate_rewrite


def test_validate_rewrite_success() -> None:
    body = " ".join(["слово"] * 100)
    text = f"✈️ Заголовок\n\n📍 Подробности: {body}\n\n#авиация #происшествие #небонаграни #авиабезопасность"
    ok, reason = validate_rewrite(text)
    assert ok is True
    assert reason == "ok"


def test_validate_rewrite_too_short() -> None:
    text = "✈️ Коротко\n\n📍 мало слов\n#авиация #происшествие #небонаграни #авиабезопасность"
    ok, reason = validate_rewrite(text)
    assert ok is False
    assert reason == "too_short"
