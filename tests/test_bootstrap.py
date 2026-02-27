from pathlib import Path

from app.bootstrap import load_dotenv


def test_load_dotenv_sets_missing_vars(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("A=1\nB=hello\n", encoding="utf-8")
    monkeypatch.delenv("A", raising=False)

    load_dotenv(str(env_file))

    assert __import__("os").environ["A"] == "1"
    assert __import__("os").environ["B"] == "hello"


def test_load_dotenv_does_not_override_existing(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("A=2\n", encoding="utf-8")
    monkeypatch.setenv("A", "keep")

    load_dotenv(str(env_file))

    assert __import__("os").environ["A"] == "keep"
