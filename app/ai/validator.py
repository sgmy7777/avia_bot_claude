from __future__ import annotations


REQUIRED_HASHTAGS = ("#авиация", "#происшествие", "#небонаграни", "#авиабезопасность")
REQUIRED_EMOJIS = ("✈️", "📍")  # ⚠️ опционален — только если есть пострадавшие


def validate_rewrite(text: str, min_words: int = 60) -> tuple[bool, str]:
    words = text.split()
    if len(words) < min_words:
        return False, f"too_short (got {len(words)}, need {min_words})"
    if len(words) > 350:
        return False, f"too_long (got {len(words)})"
    if any(tag not in text for tag in REQUIRED_HASHTAGS):
        missing = [tag for tag in REQUIRED_HASHTAGS if tag not in text]
        return False, f"missing_required_hashtags: {missing}"
    if any(emoji not in text for emoji in REQUIRED_EMOJIS):
        missing = [e for e in REQUIRED_EMOJIS if e not in text]
        return False, f"missing_format_markers: {missing}"
    return True, "ok"


def validate_fallback(text: str) -> tuple[bool, str]:
    """Валидация для fallback-текста с мягким порогом."""
    return validate_rewrite(text, min_words=40)
