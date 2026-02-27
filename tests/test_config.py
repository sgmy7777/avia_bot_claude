from app.config import _default_asn_feed_urls, _parse_bool, _parse_csv


def test_parse_bool_true_values(monkeypatch) -> None:
    monkeypatch.setenv("FLAG", "yes")
    assert _parse_bool("FLAG", False) is True


def test_parse_bool_default(monkeypatch) -> None:
    monkeypatch.delenv("FLAG", raising=False)
    assert _parse_bool("FLAG", True) is True


def test_parse_csv(monkeypatch) -> None:
    monkeypatch.setenv("CSV", "a, b, ,c")
    assert _parse_csv("CSV", "x") == ["a", "b", "c"]


def test_default_asn_feed_urls_contains_current_year_path() -> None:
    value = _default_asn_feed_urls()
    assert "https://aviation-safety.net/rss.xml" in value
    assert "/asndb/year/" in value


def test_default_llm_provider_auto(monkeypatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    from app.config import Settings

    settings = Settings.from_env()
    assert settings.llm_provider == "auto"


def test_default_publication_limits(monkeypatch) -> None:
    monkeypatch.delenv("MAX_PUBLICATIONS_PER_CYCLE", raising=False)
    monkeypatch.delenv("DATE_WINDOW_DAYS", raising=False)
    from app.config import Settings

    settings = Settings.from_env()
    assert settings.max_publications_per_cycle == 10
    assert settings.date_window_days == 1
