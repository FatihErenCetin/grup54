from ensemble.config import Settings, get_settings


def test_default_mode_is_local(monkeypatch):
    monkeypatch.delenv("ENSEMBLE_MODE", raising=False)
    assert Settings(_env_file=None).ENSEMBLE_MODE == "local"


def test_env_overrides_default(monkeypatch):
    monkeypatch.setenv("ENSEMBLE_MODE", "hosted")
    assert Settings(_env_file=None).ENSEMBLE_MODE == "hosted"


def test_get_settings_cached():
    assert get_settings() is get_settings()
