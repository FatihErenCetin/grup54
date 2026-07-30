"""K6 KAPISI — insan onayı olmadan diske HİÇBİR ŞEY yazılmaz (#340, §8.5).

Bu dosya reponun en yüksek bahisli kilidini korur: "AI taslaklar, insan
onaylar" (K6, KİLİTLİ). Kilit iki katmanda sınanır — saf fonksiyon
(`apply.harness_yaz`) ve HTTP ucu (`POST /onboarding/uygula`) — çünkü ikisi
ayrı yollardan atlatılabilir.

MUTASYON KANITI (elle koşuldu, #340): `apply.py`'deki
    if onay.onaylandi is not True: raise OnaysizYazmaHatasi(...)
satırları silindiğinde bu dosyadaki üç test birden düşer (onaysız çağrı
sessizce dosya yazar). Yani testler kilidin KENDİSİNİ ölçüyor, kilidin
etrafındaki dekoru değil.
"""

import pytest
from fastapi.testclient import TestClient

from ensemble.api.routers.onboarding import get_onboarding_root
from ensemble.app import create_app
from ensemble.config import Settings
from ensemble.onboarding.apply import (
    MevcutDosyaHatasi,
    OnayKaydi,
    OnaysizYazmaHatasi,
    harness_yaz,
)
from ensemble.onboarding.intake import Brief, Kisitlar
from ensemble.onboarding.sprint_plan import Kapasite, sprint_dagit
from ensemble.onboarding.story import Epic, StoryTaslagi, UserStory


def _brief() -> Brief:
    return Brief(
        urun_tek_cumle="Ekipler için ortak proje beyni.",
        hedef_kullanicilar=["geliştirici"],
        cekirdek_ozellikler=["radar", "board", "scope"],
        kapsam_disi=["mobil uygulama"],
        kisitlar=Kisitlar(ekip_buyuklugu=4, sprint_sayisi=2),
        basari_hedefi="Canlı demoda çakışma radarda görünsün.",
    )


def _taslak() -> StoryTaslagi:
    return StoryTaslagi(
        epicler=[Epic(id="E1", baslik="Radar")],
        storyler=[
            UserStory(
                id="US1",
                epic_id="E1",
                rol="geliştirici",
                istek="aynı dosyaya dokunan başka birini görmek",
                fayda="çakışmayı merge'den önce fark edeyim",
                kabul_kriterleri=["Radar sayfasında kart görünür"],
                puan=5,
                oncelik=1,
            ),
            UserStory(
                id="US2",
                epic_id="E1",
                rol="takım lideri",
                istek="board'un kendiliğinden dolmasını",
                fayda="kart taşımakla uğraşmayayım",
                kabul_kriterleri=["PR açılınca kart In Progress'e geçer"],
                puan=3,
                oncelik=2,
            ),
        ],
    )


def _client(tmp_path) -> TestClient:
    app = create_app(Settings(_env_file=None, ENSEMBLE_MODE="local"))
    app.dependency_overrides[get_onboarding_root] = lambda: tmp_path
    return TestClient(app)


# --- 1) Saf fonksiyon katmanı --------------------------------------------


def test_onaysiz_yazma_diske_dokunmaz(tmp_path):
    """K6: `onaylandi=False` -> istisna VE `.harness/` hiç oluşmaz.

    İkinci iddia birincisi kadar önemli: reddedilen bir istek yarım bir
    `.harness/` bırakırsa `wizard.init_harness`'in "zaten var -> dokunma"
    fail-safe'i sonraki gerçek kurulumu sessizce atlar (#57 review dersi).
    """
    with pytest.raises(OnaysizYazmaHatasi):
        harness_yaz(
            tmp_path,
            brief=_brief(),
            taslak=_taslak(),
            plan=None,
            onay=OnayKaydi(onaylandi=False, onaylayan="fatih"),
        )
    assert not (tmp_path / ".harness").exists()


def test_onay_alani_hic_verilmezse_de_yazilmaz(tmp_path):
    """Varsayılan `onaylandi=False` — "unutulan onay" yazmaya dönüşmez."""
    with pytest.raises(OnaysizYazmaHatasi):
        harness_yaz(
            tmp_path, brief=_brief(), taslak=_taslak(), plan=None, onay=OnayKaydi()
        )
    assert not (tmp_path / ".harness").exists()


def test_onayli_yazma_scope_ve_task_uretir(tmp_path):
    plan = sprint_dagit(
        _taslak().storyler, Kapasite(ekip_buyuklugu=4, sprint_sayisi=2)
    )
    sonuc = harness_yaz(
        tmp_path,
        brief=_brief(),
        taslak=_taslak(),
        plan=plan,
        onay=OnayKaydi(onaylandi=True, onaylayan="fatih"),
    )

    scope_dosyalari = sorted((tmp_path / ".harness" / "scope").glob("*.md"))
    task_dosyalari = sorted((tmp_path / ".harness" / "tasks").glob("*.md"))
    assert scope_dosyalari, "kapsam belgesi yazılmadı"
    assert len(task_dosyalari) == 2, "her story için bir görev dosyası bekleniyor"
    assert sonuc.yazilan

    metin = scope_dosyalari[0].read_text(encoding="utf-8")
    # Kanonik user-story cümlesi dosyada AYNEN durmalı (§8.5 kalıbı).
    assert "Bir geliştirici olarak" in metin or "Bir takım lideri olarak" in metin
    assert "böylece" in metin
    # Taslak olduğu dosyanın İÇİNDE yazar — commit eden insan neyi
    # dondurduğunu bilsin.
    assert "TASLAK" in metin


def test_varsayimlar_yazilan_belgede_isaretli_kalir(tmp_path):
    from ensemble.onboarding.intake import Varsayim

    brief = _brief()
    brief.varsayimlar = [
        Varsayim(
            alan="kapsam_disi",
            deger_ozeti="mobil uygulama yapılmayacak",
            gerekce="metinde mobilden hiç söz edilmedi",
        )
    ]
    harness_yaz(
        tmp_path,
        brief=brief,
        taslak=_taslak(),
        plan=None,
        onay=OnayKaydi(onaylandi=True, onaylayan="fatih"),
    )
    metin = (tmp_path / ".harness" / "scope" / "sprint-1.md").read_text(encoding="utf-8")
    assert "AI varsayımları" in metin
    assert "metinde mobilden hiç söz edilmedi" in metin


def test_mevcut_kapsam_belgesi_ezilmez(tmp_path):
    """PO'nun dondurduğu kapsamı bir sihirbaz taslağı EZEMEZ."""
    harness_yaz(
        tmp_path,
        brief=_brief(),
        taslak=_taslak(),
        plan=None,
        onay=OnayKaydi(onaylandi=True, onaylayan="fatih"),
    )
    onceki = (tmp_path / ".harness" / "scope" / "sprint-1.md").read_text(encoding="utf-8")

    with pytest.raises(MevcutDosyaHatasi):
        harness_yaz(
            tmp_path,
            brief=_brief(),
            taslak=_taslak(),
            plan=None,
            onay=OnayKaydi(onaylandi=True, onaylayan="fatih"),
        )
    assert (
        tmp_path / ".harness" / "scope" / "sprint-1.md"
    ).read_text(encoding="utf-8") == onceki


# --- 2) HTTP katmanı ------------------------------------------------------


def test_http_onaysiz_403_ve_dosya_yok(tmp_path):
    cevap = _client(tmp_path).post(
        "/onboarding/uygula",
        json={
            "onay": {"onaylandi": False, "onaylayan": "fatih"},
            "brief": _brief().model_dump(mode="json"),
            "taslak": _taslak().model_dump(mode="json"),
            "plan": None,
        },
    )
    assert cevap.status_code == 403
    assert not (tmp_path / ".harness").exists()


def test_http_onayli_yazar(tmp_path):
    cevap = _client(tmp_path).post(
        "/onboarding/uygula",
        json={
            "onay": {"onaylandi": True, "onaylayan": "fatih"},
            "brief": _brief().model_dump(mode="json"),
            "taslak": _taslak().model_dump(mode="json"),
            "plan": None,
        },
    )
    assert cevap.status_code == 200, cevap.text
    assert cevap.json()["task_dosyalari"]
    assert (tmp_path / ".harness" / "tasks").is_dir()


def test_hosted_modda_yazma_ucu_yok(tmp_path):
    """Paylaşılan demoda hiç kimse sunucunun `.harness/`'ine yazamaz."""
    app = create_app(
        Settings(
            _env_file=None,
            ENSEMBLE_MODE="hosted",
            CORS_ORIGINS=["https://recommend2me.com"],
        )
    )
    app.dependency_overrides[get_onboarding_root] = lambda: tmp_path
    cevap = TestClient(app).post(
        "/onboarding/uygula",
        json={
            "onay": {"onaylandi": True, "onaylayan": "saldirgan"},
            "brief": _brief().model_dump(mode="json"),
            "taslak": _taslak().model_dump(mode="json"),
            "plan": None,
        },
    )
    assert cevap.status_code == 404
    assert not (tmp_path / ".harness").exists()


def test_taslak_uretim_uclari_diske_hic_dokunmaz(tmp_path):
    """K6'nın ikinci yarısı: onaydan ÖNCEKİ adımların hiçbiri yazmaz."""
    client = _client(tmp_path)
    client.post("/onboarding/sorular", json={"mod": "soru_cevap", "tur": 1})
    client.post(
        "/onboarding/brief",
        json={"mod": "kendim", "brief": _brief().model_dump(mode="json")},
    )
    client.post(
        "/onboarding/plan",
        json={
            "storyler": [s.model_dump(mode="json") for s in _taslak().storyler],
            "kapasite": {"ekip_buyuklugu": 4, "sprint_sayisi": 2},
        },
    )
    assert not (tmp_path / ".harness").exists()
