"""Config validation: missing token must be a polite exit, not a traceback."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from core.config import (
    DEFAULT_LOG_LEVEL,
    DEFAULT_MODULES,
    DEFAULT_STORAGE_PATH,
    ConfigError,
    load_env_file,
    load_settings,
    load_settings_or_exit,
)


def test_missing_token_exits_with_code_1(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        load_settings_or_exit({})

    assert exit_info.value.code == 1
    assert "BOT_TOKEN" in capsys.readouterr().err


def test_blank_token_is_rejected() -> None:
    with pytest.raises(ConfigError):
        load_settings({"BOT_TOKEN": "   "})


def test_defaults_are_applied() -> None:
    settings = load_settings({"BOT_TOKEN": "42:TEST"})

    assert settings.bot_token == "42:TEST"
    assert settings.modules == DEFAULT_MODULES
    assert settings.log_level == DEFAULT_LOG_LEVEL
    assert settings.storage_path == DEFAULT_STORAGE_PATH


def test_modules_are_normalized_and_deduplicated() -> None:
    settings = load_settings({"BOT_TOKEN": "42:TEST", "MODULES": " Health , extra ,health, "})

    assert settings.modules == ("health", "extra")


def test_unknown_log_level_falls_back_to_info() -> None:
    settings = load_settings({"BOT_TOKEN": "42:TEST", "LOG_LEVEL": "verbose"})

    assert settings.log_level == "INFO"


def test_missing_env_file_is_not_an_error(tmp_path: Path) -> None:
    assert load_env_file(tmp_path / "absent.env") is None


def test_env_file_fills_gaps_but_real_env_wins(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("BOT_TOKEN=42:FROM-FILE\nLOG_LEVEL=DEBUG\n", encoding="utf-8")
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.setenv("LOG_LEVEL", "WARNING")

    assert load_env_file(env_file) == env_file

    settings = load_settings(os.environ)
    assert settings.bot_token == "42:FROM-FILE"
    assert settings.log_level == "WARNING"
