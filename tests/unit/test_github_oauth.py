"""GitHub App kullanıcı-yetkilendirme akışı (#79 daraltılmış dilim) —
integrations/github/oauth.py testleri.

GERÇEK AĞ ÇAĞRISI YOK — httpx.MockTransport (test_ollama_adapter.py /
test_github_auth.py deseni).
"""

import httpx
import pytest

from ensemble.config import Settings
from ensemble.integrations.github.errors import GitHubAuthError, GitHubTransientError
from ensemble.integrations.github.oauth import (
    build_authorize_url,
    exchange_code_for_token,
    fetch_github_user,
)


def _settings(**overrides) -> Settings:
    values = {
        "GITHUB_OAUTH_CLIENT_ID": "client-123",
        "GITHUB_OAUTH_CLIENT_SECRET": "secret-abc",
        **overrides,
    }
    return Settings(_env_file=None, **values)


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_build_authorize_url_gerekli_parametreleri_tasir():
    url = build_authorize_url(
        _settings(), redirect_uri="https://api.example.com/auth/callback", state="s3cr3t-state"
    )
    assert url.startswith("https://github.com/login/oauth/authorize?")
    assert "client_id=client-123" in url
    assert "state=s3cr3t-state" in url
    assert "redirect_uri=https%3A%2F%2Fapi.example.com%2Fauth%2Fcallback" in url


def test_exchange_code_for_token_mutlu_yol():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"access_token": "gho_abc123", "token_type": "bearer"})

    token = exchange_code_for_token(
        _settings(),
        code="the-code",
        redirect_uri="https://api.example.com/auth/callback",
        http_client=_client(handler),
    )

    assert token == "gho_abc123"
    assert seen["url"] == "https://github.com/login/oauth/access_token"
    assert "client_secret=secret-abc" in seen["body"]
    assert "code=the-code" in seen["body"]


def test_exchange_code_for_token_govdede_error_alani_reddedilir():
    """GitHub kod reddini 200 status + govdede {"error": ...} ile bildirir —
    HTTP hata kodu DEĞİL; bu yüzden raise_for_status YETMEZ, ayrı kontrol şart."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"error": "bad_verification_code", "error_description": "kod süresi doldu"},
        )

    with pytest.raises(GitHubAuthError, match="kod süresi doldu"):
        exchange_code_for_token(
            _settings(),
            code="expired-code",
            redirect_uri="https://api.example.com/auth/callback",
            http_client=_client(handler),
        )


def test_exchange_code_for_token_access_token_yoksa_reddedilir():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"token_type": "bearer"})

    with pytest.raises(GitHubAuthError, match="access_token yok"):
        exchange_code_for_token(
            _settings(),
            code="c",
            redirect_uri="https://api.example.com/auth/callback",
            http_client=_client(handler),
        )


def test_exchange_code_for_token_5xx_transient_hataya_donusur():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream down")

    with pytest.raises(GitHubTransientError):
        exchange_code_for_token(
            _settings(),
            code="c",
            redirect_uri="https://api.example.com/auth/callback",
            http_client=_client(handler),
        )


def test_fetch_github_user_mutlu_yol():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth_header"] = request.headers.get("authorization")
        return httpx.Response(
            200, json={"login": "esma6", "avatar_url": "https://avatars.example/esma6.png"}
        )

    handle, avatar_url = fetch_github_user("gho_abc123", http_client=_client(handler))

    assert handle == "esma6"
    assert avatar_url == "https://avatars.example/esma6.png"
    assert seen["auth_header"] == "Bearer gho_abc123"


def test_fetch_github_user_avatar_yoksa_none_doner():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"login": "esma6"})

    handle, avatar_url = fetch_github_user("tok", http_client=_client(handler))
    assert handle == "esma6"
    assert avatar_url is None


def test_fetch_github_user_401_auth_hatasina_donusur():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Bad credentials"})

    with pytest.raises(GitHubAuthError):
        fetch_github_user("kotu-token", http_client=_client(handler))
