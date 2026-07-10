from ensemble.config import Settings, get_settings


def test_default_mode_is_local(monkeypatch):
    monkeypatch.delenv("ENSEMBLE_MODE", raising=False)
    assert Settings(_env_file=None).ENSEMBLE_MODE == "local"


def test_env_overrides_default(monkeypatch):
    monkeypatch.setenv("ENSEMBLE_MODE", "hosted")
    assert Settings(_env_file=None).ENSEMBLE_MODE == "hosted"


def test_get_settings_cached():
    assert get_settings() is get_settings()


def test_github_default_branch_default():
    assert Settings(_env_file=None).GITHUB_DEFAULT_BRANCH == "main"


def test_settings_ok_without_github_app_config(monkeypatch):
    for var in ("GITHUB_APP_ID", "GITHUB_APP_PRIVATE_KEY_PATH", "GITHUB_APP_INSTALLATION_ID"):
        monkeypatch.delenv(var, raising=False)
    settings = Settings(_env_file=None)
    assert settings.GITHUB_APP_ID is None
    assert settings.GITHUB_APP_PRIVATE_KEY_PATH is None
    assert settings.GITHUB_APP_INSTALLATION_ID is None
