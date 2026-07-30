"""#332 — UÇTAN UCA: üretilen config'in komutu GERÇEKTEN bir MCP sunucusu açar mı?

NEDEN BU TEST VAR: bu projenin en pahalı hatası "motoru yaz, son santimi
bağlama" oldu. `test_settings_router.py` config metninin *ayrıştırılabildiğini*
kilitler — ama ayrıştırılabilir bir config yanlış bir komut da taşıyabilir
(modül adı değişir, `--directory` düşer, paket workspace'ten çıkar). O durumda
tüm unit testler yeşil kalır, kullanıcının aracı ise sessizce bağlanamaz.

Bu test config'i uçtan OKUR, `command` + `args`'ı BİREBİR çalıştırır ve
JSON-RPC stdio el sıkışması + `tools/list` yapar: `who_is_touching` ve
`check_scope` gerçekten görünüyor mu. `make mcp` hedefi de aynı komutu
çalıştırdığı için bu aynı zamanda o hedefin kanıtıdır.

Neden `integration` işaretli: `uv run` alt-süreci ~5-6 sn sürer ve `uv`nin
PATH'te olmasını gerektirir (yoksa skip). Varsayılan `make test` bunu koşar;
`-m "not integration"` ile ayıklanabilir.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from ensemble.app import create_app
from ensemble.config import Settings
from ensemble.store.engine import get_engine
from ensemble.store.models import Base

pytestmark = pytest.mark.integration

_INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "ensemble-test", "version": "1"},
    },
}
_INITIALIZED = {"jsonrpc": "2.0", "method": "notifications/initialized"}
_TOOLS_LIST = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}


def _uretilen_komut(tmp_path, monkeypatch) -> tuple[str, list[str]]:
    """Config'i UÇTAN alır — testin kendi komutunu kurmasına izin verilmez,
    yoksa "üretilen config çalışıyor mu" sorusu sorulmamış olur."""
    monkeypatch.setenv("HOME", str(tmp_path))
    settings = Settings(
        _env_file=None, ENSEMBLE_MODE="local", DATABASE_URL=f"sqlite:///{tmp_path / 'e.db'}"
    )
    app = create_app(settings)
    Base.metadata.create_all(get_engine(settings))
    with TestClient(app) as client:
        body = client.get("/settings/mcp").json()
    claude = next(a for a in body["araclar"] if a["arac"] == "claude-code")
    sunucu = json.loads(claude["config_metni"])["mcpServers"]["ensemble"]
    return sunucu["command"], sunucu["args"]


def test_uretilen_config_komutu_calisan_bir_mcp_sunucusu_acar(tmp_path, monkeypatch):
    """MUTASYON KİLİDİ: `mcp_clients.stdio_komutu`'nda modül adını boz
    (`ensemble_mcp.server` -> `ensemble_mcp.sunucu`) ya da `--directory`
    argümanını çıkar → alt-süreç tool listesi döndüremez → KIRMIZI. Unit
    testler (yalnız metni ayrıştıranlar) bu mutasyonda YEŞİL kalır — farkı
    yakalayan tek yer burası."""
    komut, args = _uretilen_komut(tmp_path, monkeypatch)
    if shutil.which(komut) is None:
        pytest.skip(f"`{komut}` PATH'te yok")

    girdi = "".join(json.dumps(m) + "\n" for m in (_INITIALIZE, _INITIALIZED, _TOOLS_LIST))
    sonuc = subprocess.run(
        [komut, *args],
        input=girdi,
        capture_output=True,
        text=True,
        timeout=120,
    )

    cevaplar = [json.loads(satir) for satir in sonuc.stdout.splitlines() if satir.strip()]
    kimlikler = {c.get("id"): c for c in cevaplar}
    assert 1 in kimlikler, f"initialize cevabı yok. stderr: {sonuc.stderr[-2000:]}"
    assert kimlikler[1]["result"]["serverInfo"]["name"] == "ensemble"

    assert 2 in kimlikler, f"tools/list cevabı yok. stderr: {sonuc.stderr[-2000:]}"
    tool_adlari = {t["name"] for t in kimlikler[2]["result"]["tools"]}
    assert {"who_is_touching", "check_scope"} <= tool_adlari, tool_adlari


def test_make_mcp_hedefi_uretilen_config_ile_AYNI_modulu_calistirir():
    """`make mcp` ile config'teki komut ayrışırsa kullanıcı "elde çalışıyor
    ama araçtan bağlanmıyor" (ya da tersi) tuzağına düşer. MUTASYON KİLİDİ:
    Makefile'daki `mcp:` hedefini sil ya da başka bir modüle çevir → KIRMIZI."""
    from pathlib import Path

    from ensemble import mcp_clients

    makefile = Path(__file__).resolve().parents[2] / "Makefile"
    icerik = makefile.read_text(encoding="utf-8")
    assert "\nmcp:\n" in icerik, "`make mcp` hedefi yok"
    hedef_govdesi = icerik.split("\nmcp:\n", 1)[1].split("\n\n", 1)[0]

    _, args = mcp_clients.stdio_komutu("/x")
    modul = args[-1]
    assert modul in hedef_govdesi, f"`make mcp` {modul} modülünü çalıştırmıyor"
