"""#340 "son santim": sihirbaz GERÇEK kuruluma indiğinde çalışıyor mu?

Üç şey "kodda var ≠ çalışıyor" sınıfına giriyordu:

1. **Yazma kökü.** `.harness/` bu üründe HER YERDE cwd'den okunur
   (`FileHarnessPort()` varsayılanı `"."`). macOS masaüstü paketi
   (`packaging/launcher.py`) açılışta `os.chdir(data_dir)` yapıyor — dosya
   konumundan türetilen bir kök orada .app paketinin içini gösterirdi ve
   sihirbaz, ürünün OKUDUĞU dizinden BAŞKA bir yere yazardı.
2. **Salt-okunur kök.** Düğme çalışır görünür, tıklanınca `PermissionError`
   -> 500. Önceden ölçülüp dürüstçe kapatılmalı.
3. **Maliyet kapağı.** Sihirbazın LLM çağıran uçları POST; hosted demonun
   rate-limit middleware'i yalnız GET ölçüyordu -> kapaksız kalırlardı.
"""

import os
import stat

import pytest
from fastapi.testclient import TestClient

from ensemble.api.rate_limit import AI_METERED_POST_PATHS
from ensemble.api.routers.onboarding import _varsayilan_kok, get_onboarding_root
from ensemble.app import create_app
from ensemble.config import Settings
from ensemble.onboarding.intake import Brief


def test_varsayilan_kok_cwd_yi_IZLER(tmp_path, monkeypatch):
    """Ürünün geri kalanı `FileHarnessPort()` ile cwd'den okuyor; sihirbaz da
    ORAYA yazmalı.

    ⚠️ Testin cwd'yi DEĞİŞTİRMESİ şart: pytest repo kökünden koşuyor ve orada
    `Path.cwd()` ile `Path(__file__).parents[5]` AYNI dizini veriyor — cwd
    değiştirilmeden yazılan bir iddia iki kurulumda da geçer, yani HİÇBİR ŞEY
    ölçmez (totolojik test). `monkeypatch.chdir` ikisini AYIRIR: dosya
    konumundan türetilen bir kök burada repo kökünü döndürür ve test düşer —
    masaüstü paketindeki (`os.chdir(data_dir)`) gerçek durumun aynısı.
    """
    from ensemble_shared.harness import FileHarnessPort

    monkeypatch.chdir(tmp_path)
    assert _varsayilan_kok().resolve() == tmp_path.resolve()
    # Sihirbazın YAZDIĞI kök ile ürünün OKUDUĞU kök aynı olmalı.
    assert FileHarnessPort().root.resolve() == _varsayilan_kok().resolve()


def test_salt_okunur_kokte_yazma_onceden_kapatilir(tmp_path):
    """`/durum` yazmayı kapatır ve NEDENİNİ söyler (500 beklemeden)."""
    if os.geteuid() == 0:  # pragma: no cover - CI root ise izinler anlamsız
        pytest.skip("root kullanıcı izinleri baypas eder")
    kok = tmp_path / "salt-okunur"
    kok.mkdir()
    kok.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        app = create_app(Settings(_env_file=None, ENSEMBLE_MODE="local"))
        app.dependency_overrides[get_onboarding_root] = lambda: kok
        client = TestClient(app)

        durum = client.get("/onboarding/durum").json()
        assert durum["yazma_mumkun"] is False
        assert "yazılamıyor" in (durum["yazma_engeli"] or "")

        cevap = client.post(
            "/onboarding/uygula",
            json={
                "onay": {"onaylandi": True, "onaylayan": "fatih"},
                "brief": Brief().model_dump(mode="json"),
                "taslak": {"epicler": [], "storyler": [], "dusenler": []},
                "plan": None,
            },
        )
        assert cevap.status_code == 409
        assert "yazılamıyor" in cevap.json()["message"]
    finally:
        kok.chmod(stat.S_IRWXU)


def test_yazilabilir_kokte_engel_yok(tmp_path):
    app = create_app(Settings(_env_file=None, ENSEMBLE_MODE="local"))
    app.dependency_overrides[get_onboarding_root] = lambda: tmp_path
    durum = TestClient(app).get("/onboarding/durum").json()
    assert durum["yazma_mumkun"] is True
    assert durum["yazma_engeli"] is None


def test_hosted_modda_engel_metinle_beyan_edilir(tmp_path):
    app = create_app(
        Settings(
            _env_file=None,
            ENSEMBLE_MODE="hosted",
            CORS_ORIGINS=["https://recommend2me.com"],
        )
    )
    app.dependency_overrides[get_onboarding_root] = lambda: tmp_path
    durum = TestClient(app).get("/onboarding/durum").json()
    assert durum["yazma_mumkun"] is False
    assert "hosted" in durum["yazma_engeli"]


def _demo_client(tmp_path) -> TestClient:
    app = create_app(
        Settings(
            _env_file=None,
            ENSEMBLE_MODE="hosted",
            DEMO_MODE=True,
            GITHUB_REPO_OWNER="grup54",
            GITHUB_REPO_NAME="ensemble",
            CORS_ORIGINS=["https://recommend2me.com"],
            DEMO_AI_RATE_LIMIT=2,
            DEMO_AI_GLOBAL_LIMIT=100,
            DEMO_RATE_WINDOW_S=600,
        )
    )
    app.dependency_overrides[get_onboarding_root] = lambda: tmp_path
    return TestClient(app)


def test_ai_cagiran_post_uclari_demo_kovasinda(tmp_path):
    """Maliyet kapağı: kullanıcı-girdili + LLM çağıran POST'lar ölçülür."""
    assert AI_METERED_POST_PATHS == {"/onboarding/brief", "/onboarding/taslak"}
    client = _demo_client(tmp_path)
    govde = {"mod": "kendim", "brief": Brief().model_dump(mode="json")}

    kodlar = [client.post("/onboarding/brief", json=govde).status_code for _ in range(4)]
    assert 429 in kodlar, f"AI kovası POST'u ölçmüyor: {kodlar}"


def test_deterministik_uclar_kovaya_takilmaz(tmp_path):
    """`/sorular` ve `/plan` ağsız ve LLM'siz — demo kovasına girmemeli, yoksa
    sihirbazın ÜCRETSİZ adımları da kesilirdi."""
    client = _demo_client(tmp_path)
    govde = {"mod": "soru_cevap", "tur": 1, "brief": Brief().model_dump(mode="json")}
    kodlar = [client.post("/onboarding/sorular", json=govde).status_code for _ in range(6)]
    assert kodlar == [200] * 6
