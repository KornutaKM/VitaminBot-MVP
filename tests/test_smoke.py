import pytest

from vitaminbot import __version__
from vitaminbot.config import Settings
from vitaminbot.main import healthcheck


def test_package_version_is_defined() -> None:
    assert __version__ == "0.1.0"


def test_healthcheck_is_ok() -> None:
    assert healthcheck() == {"status": "ok"}


def test_settings_are_loaded_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/vitaminbot")

    settings = Settings.from_environment()

    assert settings.app_env == "test"
    assert settings.database_url == "postgresql://example.invalid/vitaminbot"
