from datetime import datetime, timezone

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from ensemble.config import Settings
from ensemble.integrations.github.auth import InstallationTokenCache
from ensemble.integrations.github.errors import GitHubConfigError


def _generate_pem() -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )


@pytest.fixture
def pem_path(tmp_path):
    path = tmp_path / "test-key.pem"
    path.write_bytes(_generate_pem())
    return str(path)


@pytest.fixture
def pem_content() -> str:
    return _generate_pem().decode()


def _settings(pem_path: str) -> Settings:
    return Settings(
        _env_file=None,
        GITHUB_APP_ID="12345",
        GITHUB_APP_PRIVATE_KEY_PATH=pem_path,
        GITHUB_APP_INSTALLATION_ID="999",
    )


class _FakeClock:
    def __init__(self, start: float):
        self.now = start

    def __call__(self) -> float:
        return self.now


def _make_http_client(call_counter: list, expires_in_s: int, clock: _FakeClock) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        call_counter.append(1)
        expires_at = datetime.fromtimestamp(clock.now + expires_in_s, tz=timezone.utc).isoformat()
        return httpx.Response(200, json={"token": f"tok-{len(call_counter)}", "expires_at": expires_at})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_missing_config_raises_without_network():
    with pytest.raises(GitHubConfigError):
        InstallationTokenCache(Settings(_env_file=None))


def test_pem_content_env_kullanilir_path_yoksa(pem_content):
    """#186: PATH yoksa GITHUB_APP_PRIVATE_KEY (icerik) ile de dogrulanir/token uretilir."""
    settings = Settings(
        _env_file=None,
        GITHUB_APP_ID="12345",
        GITHUB_APP_PRIVATE_KEY=pem_content,
        GITHUB_APP_INSTALLATION_ID="999",
    )
    clock = _FakeClock(start=1_000_000.0)
    calls: list = []
    http_client = _make_http_client(calls, expires_in_s=3600, clock=clock)
    cache = InstallationTokenCache(settings, http_client=http_client, clock=clock)

    token = cache.get_token()

    assert token == "tok-1"
    assert len(calls) == 1


def test_path_content_ikisi_de_yoksa_config_error():
    with pytest.raises(GitHubConfigError):
        InstallationTokenCache(
            Settings(_env_file=None, GITHUB_APP_ID="1", GITHUB_APP_INSTALLATION_ID="2")
        )


def test_path_varsa_content_yerine_path_kullanilir(pem_path, pem_content):
    """PATH ve content ikisi de doluysa PATH kazanir (mevcut local akis korunur)."""
    settings = Settings(
        _env_file=None,
        GITHUB_APP_ID="12345",
        GITHUB_APP_PRIVATE_KEY_PATH=pem_path,
        GITHUB_APP_PRIVATE_KEY="bu-gecersiz-icerik-kullanilmamali",
        GITHUB_APP_INSTALLATION_ID="999",
    )
    clock = _FakeClock(start=1_000_000.0)
    calls: list = []
    http_client = _make_http_client(calls, expires_in_s=3600, clock=clock)
    cache = InstallationTokenCache(settings, http_client=http_client, clock=clock)

    token = cache.get_token()  # gecersiz content kullanilsaydi jwt.encode patlardi

    assert token == "tok-1"


def test_token_is_cached_within_expiry(pem_path):
    clock = _FakeClock(start=1_000_000.0)
    calls: list = []
    http_client = _make_http_client(calls, expires_in_s=3600, clock=clock)
    cache = InstallationTokenCache(_settings(pem_path), http_client=http_client, clock=clock)

    tok1 = cache.get_token()
    tok2 = cache.get_token()

    assert tok1 == tok2
    assert len(calls) == 1


def test_token_refreshed_after_expiry(pem_path):
    clock = _FakeClock(start=1_000_000.0)
    calls: list = []
    http_client = _make_http_client(calls, expires_in_s=3600, clock=clock)
    cache = InstallationTokenCache(_settings(pem_path), http_client=http_client, clock=clock)

    tok1 = cache.get_token()
    clock.now += 3600 - 30  # sure dolmaya 30sn kala - 60sn payin icinde, yenilenmeli
    tok2 = cache.get_token()

    assert tok1 != tok2
    assert len(calls) == 2
