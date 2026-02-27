from app.ai.validator import validate_rewrite, validate_fallback, REQUIRED_HASHTAGS


def _base_text(word_count: int) -> str:
    body = " ".join(["слово"] * word_count)
    return f"✈️ Заголовок\n\n📍 Подробности: {body}\n\n#авиация #происшествие #небонаграни #авиабезопасность"


def test_validate_rewrite_success() -> None:
    ok, reason = validate_rewrite(_base_text(100))
    assert ok is True
    assert reason == "ok"


def test_validate_rewrite_too_short() -> None:
    ok, reason = validate_rewrite(_base_text(10))
    assert ok is False
    assert "too_short" in reason


def test_validate_rewrite_custom_min_words() -> None:
    """fix #6: можно переопределить порог."""
    ok, _ = validate_rewrite(_base_text(50), min_words=40)
    assert ok is True


def test_validate_fallback_passes_for_short_text() -> None:
    """fix #6: fallback-текст (~60 слов) проходит мягкую валидацию."""
    ok, reason = validate_fallback(_base_text(45))
    assert ok is True, f"Fallback should pass: {reason}"


def test_validate_rewrite_too_long() -> None:
    ok, reason = validate_rewrite(_base_text(400))
    assert ok is False
    assert "too_long" in reason


def test_validate_missing_hashtag() -> None:
    text = "✈️ Заголовок\n\n📍 Подробности: " + " ".join(["слово"] * 100) + "\n\n#авиация"
    ok, reason = validate_rewrite(text)
    assert ok is False
    assert "hashtag" in reason


def test_validate_missing_emoji() -> None:
    body = " ".join(["слово"] * 100)
    text = f"Заголовок без эмодзи\n\nПодробности: {body}\n\n#авиация #происшествие #небонаграни #авиабезопасность"
    ok, reason = validate_rewrite(text)
    assert ok is False
    assert "format_markers" in reason
