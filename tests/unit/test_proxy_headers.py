"""#335 — uvicorn proxy başlığı güveni: OLMAYINCA GitHub girişi çalışmıyor.

Bu bir davranış testi DEĞİL, bir KONFİGÜRASYON kilidi — ve bilerek öyle:
kusur kodda değil, container'ın başlatma komutundaydı. Ölçüm (29 Tem, canlı):

    /auth/login  ->  redirect_uri=http%3A%2F%2Fapi.recommend2me.com%2F...
                                  ^^^^ HTTPS DEGIL  ->  GitHub reddediyor

`request.url_for()` şemayı ASGI scope'undan okur; uvicorn `X-Forwarded-Proto`
başlığına yalnız `--forwarded-allow-ips` içindeki peer'lardan güvenir ve
varsayılan `127.0.0.1`'dir — Caddy docker ağından bağlandığı için başlık
sessizce yok sayılıyordu.

`test_harness_git.py` ile aynı desen: prodüksiyon davranışını belirleyen ama
Python'dan çağrılmayan bir satırı testle kilitle.
"""

from pathlib import Path

import pytest

DOCKERFILE = Path(__file__).resolve().parents[2] / "Dockerfile"


@pytest.fixture(scope="module")
def prod_cmd() -> str:
    satirlar = [
        s for s in DOCKERFILE.read_text(encoding="utf-8").splitlines()
        if s.startswith("CMD [") and "uvicorn" in s
    ]
    assert len(satirlar) == 1, f"tek bir prod CMD bekleniyordu, bulunan: {len(satirlar)}"
    return satirlar[0]


def test_prod_cmd_forwarded_allow_ips_tasir(prod_cmd: str) -> None:
    """MUTASYON KİLİDİ: bayrağı CMD'den sil → bu test düşer ve canlıda
    `redirect_uri` yeniden `http://` üretmeye başlar (GitHub girişi kırılır)."""
    assert "--forwarded-allow-ips" in prod_cmd


def test_prod_cmd_proxy_headers_acik(prod_cmd: str) -> None:
    """Uvicorn'da varsayılan açık olsa da AÇIKÇA yazılır: bu satır, arkasında
    bir ters-proxy olduğunu okuyana söyleyen tek yerdir."""
    assert "--proxy-headers" in prod_cmd


def test_prod_cmd_hala_exec_form_ve_PORT_genislemesi_korunur(prod_cmd: str) -> None:
    """Yeni bayraklar eklenirken mevcut iki garanti bozulmamalı:
    `exec` (PID 1 uvicorn olur → SIGTERM doğrudan ona gider, graceful shutdown)
    ve `${PORT:-8000}` genişletmesi (compose PORT enjekte eder)."""
    assert "exec uvicorn" in prod_cmd
    assert "${PORT:-8000}" in prod_cmd
