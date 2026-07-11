import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import httpx
import jwt

from ensemble.config import Settings
from ensemble.integrations.github.client import raise_for_status
from ensemble.integrations.github.errors import GitHubConfigError

_EXPIRY_BUFFER_S = 60


class InstallationTokenCache:
    """App JWT (RS256) -> installation access token.

    Token ~1 saatlik - `expires_at`'e gore 60sn payla cache'lenir, sure
    dolunca otomatik yenilenir. `/app/installations` kesif cagrisi atlanir -
    installation_id zaten `.env`'de (#46 App kaydindan).
    """

    def __init__(
        self,
        settings: Settings,
        http_client: httpx.Client | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not (
            settings.GITHUB_APP_ID
            and settings.GITHUB_APP_PRIVATE_KEY_PATH
            and settings.GITHUB_APP_INSTALLATION_ID
        ):
            raise GitHubConfigError(
                "GITHUB_APP_ID/GITHUB_APP_PRIVATE_KEY_PATH/GITHUB_APP_INSTALLATION_ID eksik"
            )
        self._settings = settings
        self._http = http_client or httpx.Client(timeout=15.0)
        self._clock = clock
        self._lock = threading.Lock()
        self._token: str | None = None
        self._expires_at: float = 0.0

    def get_token(self) -> str:
        with self._lock:
            if self._token and self._expires_at - self._clock() > _EXPIRY_BUFFER_S:
                return self._token
            self._token, self._expires_at = self._fetch_new_token()
            return self._token

    def _build_app_jwt(self) -> str:
        pem = Path(self._settings.GITHUB_APP_PRIVATE_KEY_PATH).read_text()
        now = int(self._clock())
        return jwt.encode(
            {"iat": now - 60, "exp": now + 540, "iss": self._settings.GITHUB_APP_ID},
            pem,
            algorithm="RS256",
        )

    def _fetch_new_token(self) -> tuple[str, float]:
        app_jwt = self._build_app_jwt()
        headers = {"Authorization": f"Bearer {app_jwt}", "Accept": "application/vnd.github+json"}
        url = (
            "https://api.github.com/app/installations/"
            f"{self._settings.GITHUB_APP_INSTALLATION_ID}/access_tokens"
        )
        resp = self._http.post(url, headers=headers)
        raise_for_status(resp)
        data = resp.json()
        expires_at = datetime.fromisoformat(data["expires_at"]).timestamp()
        return data["token"], expires_at
