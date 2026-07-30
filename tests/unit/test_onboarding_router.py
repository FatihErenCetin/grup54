"""Sihirbaz HTTP akışı (#340, §8.5): üç giriş modu + degraded beyanı.

İki iddia burada kilitleniyor:
  1. **Üç mod da çalışır** ve ikisi (soru-cevap · kendim girerim) LLM'e HİÇ
     dokunmaz — kota bittiğinde sihirbaz yarısı ölü bir ekran olmaz.
  2. **Sessiz düşüş yok:** sağlayıcı yoksa/düştüyse cevap 200 döner ama
     `degraded` DOLUDUR ve taslak boştur (uydurma taslak üretilmez).
"""

import pytest
from fastapi.testclient import TestClient

from ensemble.app import create_app
from ensemble.config import Settings
from ensemble.onboarding.drafter import TaslakUretilemedi
from ensemble.onboarding.intake import ALAN_IDLERI, Brief, Kisitlar
from ensemble.onboarding.story import Epic, StoryTaslagi, UserStory


class _SayaclıDrafter:
    """Çağrıldığını SAYAN sahte drafter — "LLM çağrılmadı" iddiasının ölçüsü."""

    def __init__(self, brief: Brief | None = None, taslak: StoryTaslagi | None = None):
        self.brief_cagri = 0
        self.story_cagri = 0
        self._brief = brief
        self._taslak = taslak

    def brief_uret(self, *, serbest_metin, mevcut, varsayimlarla_doldur):
        self.brief_cagri += 1
        if self._brief is None:
            raise TaslakUretilemedi("gemini: 429 günlük kota bitti")
        return self._brief

    def story_uret(self, brief):
        self.story_cagri += 1
        if self._taslak is None:
            raise TaslakUretilemedi("gemini+groq: iki sağlayıcı da taslak üretemedi")
        return self._taslak


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, ENSEMBLE_MODE="local")))


def _kur(monkeypatch, drafter):
    monkeypatch.setattr(
        "ensemble.api.routers.onboarding.build_drafter", lambda settings: drafter
    )
    return drafter


def _dolu_brief_json() -> dict:
    return Brief(
        urun_tek_cumle="Ekipler için ortak proje beyni.",
        hedef_kullanicilar=["geliştirici"],
        cekirdek_ozellikler=["radar", "board", "scope"],
        kapsam_disi=["mobil uygulama"],
        kisitlar=Kisitlar(ekip_buyuklugu=4, sprint_sayisi=3),
        basari_hedefi="Canlı demoda çakışma radarda görünsün.",
    ).model_dump(mode="json")


# --- Mod 1: Soru-cevap ----------------------------------------------------


def test_soru_cevap_ilk_tur_alti_ana_soru(client):
    cevap = client.post("/onboarding/sorular", json={"mod": "soru_cevap", "tur": 1})
    assert cevap.status_code == 200
    assert [s["alan"] for s in cevap.json()["sorular"]] == list(ALAN_IDLERI)


def test_soru_turu_ucuncude_biter(client):
    cevap = client.post(
        "/onboarding/sorular", json={"mod": "soru_cevap", "tur": 3, "brief": Brief().model_dump()}
    )
    veri = cevap.json()
    assert veri["sorular"] == []
    assert veri["tur_bitti"] is True


def test_soru_cevap_modu_llm_cagirmaz(client, monkeypatch):
    drafter = _kur(monkeypatch, _SayaclıDrafter())
    cevap = client.post(
        "/onboarding/brief",
        json={
            "mod": "soru_cevap",
            "cevaplar": {
                "urun_tek_cumle": "Ekipler için ortak proje beyni.",
                "hedef_kullanicilar": "geliştirici\nürün sahibi",
                "cekirdek_ozellikler": "radar\nboard\nscope",
                "kapsam_disi": "mobil uygulama",
                "kisitlar": "4 kişi, 3 sprint",
                "basari_hedefi": "Canlı demoda çakışma radarda görünsün.",
            },
        },
    )
    veri = cevap.json()
    assert cevap.status_code == 200
    assert drafter.brief_cagri == 0, "soru-cevap modu LLM çağırmamalı (kota)"
    assert veri["ai_kullanildi"] is False
    assert veri["degraded"] is None
    assert veri["eksikler"] == []
    assert veri["brief"]["kisitlar"]["ekip_buyuklugu"] == 4


# --- Mod 2: Kendim girerim ------------------------------------------------


def test_kendim_modu_llm_cagirmaz(client, monkeypatch):
    drafter = _kur(monkeypatch, _SayaclıDrafter())
    cevap = client.post(
        "/onboarding/brief", json={"mod": "kendim", "brief": _dolu_brief_json()}
    )
    assert cevap.status_code == 200
    assert drafter.brief_cagri == 0
    assert cevap.json()["ai_kullanildi"] is False


def test_eksik_alan_uydurulmaz_isaretlenir(client, monkeypatch):
    _kur(monkeypatch, _SayaclıDrafter())
    yarim = _dolu_brief_json()
    yarim["kapsam_disi"] = []
    cevap = client.post("/onboarding/brief", json={"mod": "kendim", "brief": yarim})
    veri = cevap.json()
    assert [e["alan"] for e in veri["eksikler"]] == ["kapsam_disi"]
    assert veri["brief"]["kapsam_disi"] == []  # UYDURULMADI


# --- Mod 3: Anlat ---------------------------------------------------------


def test_anlat_modu_serbest_metinden_sema_cikarir(client, monkeypatch):
    uretilen = Brief(**_dolu_brief_json())
    drafter = _kur(monkeypatch, _SayaclıDrafter(brief=uretilen))
    cevap = client.post(
        "/onboarding/brief",
        json={"mod": "anlat", "serbest_metin": "Ekipler için bir koordinasyon aracı..."},
    )
    veri = cevap.json()
    assert drafter.brief_cagri == 1, "anlat modu tam 1 LLM çağrısı yapmalı"
    assert veri["ai_kullanildi"] is True
    assert veri["brief"]["cekirdek_ozellikler"] == ["radar", "board", "scope"]
    assert veri["degraded"] is None


def test_kullanicinin_yazdigi_alan_ai_tarafindan_ezilmez(client, monkeypatch):
    uretilen = Brief(**_dolu_brief_json())
    uretilen.urun_tek_cumle = "AI'nın kendi cümlesi"
    _kur(monkeypatch, _SayaclıDrafter(brief=uretilen))
    mevcut = Brief(urun_tek_cumle="Kullanıcının kendi cümlesi.").model_dump(mode="json")

    cevap = client.post(
        "/onboarding/brief",
        json={"mod": "anlat", "serbest_metin": "...", "brief": mevcut},
    )
    assert cevap.json()["brief"]["urun_tek_cumle"] == "Kullanıcının kendi cümlesi."


def test_saglayici_dusunce_bos_ekran_degil_beyan(client, monkeypatch):
    """Kota duvarı: 200 + BOŞ taslak + DOLU `degraded` (uydurma yok)."""
    _kur(monkeypatch, _SayaclıDrafter(brief=None))
    cevap = client.post(
        "/onboarding/brief", json={"mod": "anlat", "serbest_metin": "bir şeyler"}
    )
    veri = cevap.json()
    assert cevap.status_code == 200
    assert veri["degraded"] is not None
    assert veri["degraded"]["asama"] == "brief"
    assert "kota" in veri["degraded"]["neden"]
    assert veri["ai_kullanildi"] is False


def test_saglayici_hic_yoksa_onceden_soylenir(client, monkeypatch):
    monkeypatch.setattr(
        "ensemble.api.routers.onboarding.build_drafter", lambda settings: None
    )
    durum = client.get("/onboarding/durum").json()
    assert durum["ai_kullanilabilir"] is False
    assert durum["yazma_mumkun"] is True  # local mod


# --- Story taslağı + plan -------------------------------------------------


def test_taslak_ucu_llm_dusunce_degraded_beyan_eder(client, monkeypatch):
    _kur(monkeypatch, _SayaclıDrafter(taslak=None))
    cevap = client.post("/onboarding/taslak", json={"brief": _dolu_brief_json()})
    veri = cevap.json()
    assert cevap.status_code == 200
    assert veri["taslak"]["storyler"] == []
    assert veri["degraded"]["asama"] == "story"
    assert "iki sağlayıcı" in veri["degraded"]["neden"]


def test_taslak_ucu_hayali_bagimliligi_temizler_ve_raporlar(client, monkeypatch):
    ham = StoryTaslagi(
        epicler=[Epic(id="E1", baslik="Radar")],
        storyler=[
            UserStory(
                id="US1",
                epic_id="E1",
                rol="geliştirici",
                istek="çakışmayı görmek",
                fayda="erken fark edeyim",
                kabul_kriterleri=["kart görünür"],
                puan=4,  # Fibonacci DEĞİL -> oturtulmalı
                oncelik=1,
                bagimliliklar=["US404"],  # hayali -> atılmalı
            )
        ],
    )
    _kur(monkeypatch, _SayaclıDrafter(taslak=ham))
    veri = client.post("/onboarding/taslak", json={"brief": _dolu_brief_json()}).json()

    story = veri["taslak"]["storyler"][0]
    assert story["bagimliliklar"] == []
    assert story["puan"] in (3, 5)
    # Sessiz temizlik yok: ne yapıldıysa raporlanır.
    nedenler = " ".join(d["neden"] for d in veri["taslak"]["dusenler"])
    assert "US404" in nedenler and "Fibonacci" in nedenler


def test_plan_ucu_deterministik_ve_llmsiz(client, monkeypatch):
    drafter = _kur(monkeypatch, _SayaclıDrafter())
    govde = {
        "storyler": [
            {
                "id": "US1",
                "epic_id": "E1",
                "rol": "geliştirici",
                "istek": "x",
                "fayda": "y",
                "kabul_kriterleri": [],
                "puan": 5,
                "oncelik": 1,
                "bagimliliklar": [],
            },
            {
                "id": "US2",
                "epic_id": "E1",
                "rol": "geliştirici",
                "istek": "x",
                "fayda": "y",
                "kabul_kriterleri": [],
                "puan": 3,
                "oncelik": 2,
                "bagimliliklar": [],
            },
        ],
        "kapasite": {"ekip_buyuklugu": 4, "sprint_sayisi": 2},
    }
    ilk = client.post("/onboarding/plan", json=govde)
    ikinci = client.post("/onboarding/plan", json=govde)
    assert ilk.status_code == 200
    assert ilk.json() == ikinci.json()
    assert ilk.json()["toplam_puan"] == 8
    assert drafter.story_cagri == 0 and drafter.brief_cagri == 0


def test_plan_ucu_tutarsiz_kapasiteyi_400_ile_reddeder(client):
    cevap = client.post(
        "/onboarding/plan",
        json={
            "storyler": [],
            "kapasite": {"ekip_buyuklugu": 4, "sprint_sayisi": 3, "musaitlik": [1.0]},
        },
    )
    assert cevap.status_code == 400
