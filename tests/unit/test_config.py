from ensemble.config import Settings, get_settings


def test_default_mode_is_local():
    assert Settings().ENSEMBLE_MODE == "local"


def test_get_settings_cached():
    assert get_settings() is get_settings()
