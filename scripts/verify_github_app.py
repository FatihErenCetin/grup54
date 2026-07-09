"""GitHub App kimlik zinciri doğrulaması (#46).

Kullanım: uv run --with pyjwt --with cryptography --with requests python scripts/verify_github_app.py
.env'den APP_ID / PEM yolu / INSTALLATION_ID okur; JWT → installation → anlık token → repo okuma
zincirini uçtan uca test eder. Yeni ekip üyesi .env kurulumunu bununla doğrular.
"""

import re
import time
from pathlib import Path

import jwt
import requests

ROOT = Path(__file__).resolve().parents[1]


def read_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for line in (ROOT / ".env").read_text().splitlines():
        m = re.match(r"([A-Z_]+)=(.*)", line)
        if m:
            env[m.group(1)] = m.group(2)
    return env


def main() -> None:
    env = read_env()
    app_id = env["GITHUB_APP_ID"]
    pem = (ROOT / env["GITHUB_APP_PRIVATE_KEY_PATH"]).read_text()

    now = int(time.time())
    app_jwt = jwt.encode({"iat": now - 60, "exp": now + 540, "iss": app_id}, pem, algorithm="RS256")
    h = {"Authorization": f"Bearer {app_jwt}", "Accept": "application/vnd.github+json"}

    r = requests.get("https://api.github.com/app", headers=h, timeout=15)
    r.raise_for_status()
    print(f"1) /app ✓ slug={r.json()['slug']}")

    r = requests.get("https://api.github.com/app/installations", headers=h, timeout=15)
    r.raise_for_status()
    insts = r.json()
    assert insts, "kurulum yok — App'i repoya kur (Install App)"
    iid = insts[0]["id"]
    print(f"2) installation ✓ id={iid} izinler={insts[0]['permissions']}")

    r = requests.post(
        f"https://api.github.com/app/installations/{iid}/access_tokens",
        headers=h,
        timeout=15,
    )
    r.raise_for_status()
    tok = r.json()["token"]
    print("3) anlık token ✓ (1 saatlik — kalıcı token yok)")

    th = {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"}
    r = requests.get("https://api.github.com/installation/repositories", headers=th, timeout=15)
    r.raise_for_status()
    repos = [x["full_name"] for x in r.json()["repositories"]]
    print(f"4) repo erişimi ✓ {repos}")
    print("ZİNCİR TAM ✅")


if __name__ == "__main__":
    main()
