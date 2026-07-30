"""Kapasiteye göre sprint dağıtımı (#340, §8.5 adım 4) — deterministik.

Bu testlerin varlık sebebi tam da 'LLM'e bırakılmaz' kararıdır: aşağıdaki
iddiaların hiçbiri bir modelden istenemez (aynı girdide aynı çıktı, bütçe
toplamının korunması, bağımlılık sırası).
"""

import pytest
from pydantic import ValidationError

from ensemble.onboarding.sprint_plan import Kapasite, kapasite_briefden, sprint_dagit
from ensemble.onboarding.story import UserStory


def _story(sid: str, puan: int, *, oncelik: int = 3, bagimliliklar=()) -> UserStory:
    return UserStory(
        id=sid,
        epic_id="E1",
        rol="geliştirici",
        istek=f"{sid} işini yapmak",
        fayda="işim kolaylaşsın",
        kabul_kriterleri=["ölçülebilir kriter"],
        puan=puan,
        oncelik=oncelik,
        bagimliliklar=list(bagimliliklar),
    )


def test_butcelerin_toplami_toplam_puana_esit():
    """En-büyük-kalan paylaştırma: hiçbir puan buharlaşmaz/uydurulmaz."""
    storyler = [_story(f"US{i}", 3) for i in range(1, 8)]  # 21 puan
    plan = sprint_dagit(storyler, Kapasite(ekip_buyuklugu=4, sprint_sayisi=4))
    assert sum(d.butce for d in plan.dilimler) == plan.toplam_puan == 21


def test_musaitligi_dusuk_sprint_daha_az_butce_alir():
    storyler = [_story(f"US{i}", 5) for i in range(1, 5)]  # 20 puan
    plan = sprint_dagit(
        storyler,
        Kapasite(ekip_buyuklugu=4, sprint_sayisi=2, musaitlik=[1.0, 0.5]),
    )
    butceler = [d.butce for d in plan.dilimler]
    assert butceler[0] > butceler[1]
    assert sum(butceler) == 20


def test_bagimli_story_bagimlisindan_once_gelmez():
    storyler = [
        _story("US2", 3, oncelik=1, bagimliliklar=["US1"]),
        _story("US1", 3, oncelik=5),
    ]
    plan = sprint_dagit(storyler, Kapasite(ekip_buyuklugu=2, sprint_sayisi=2))
    yerlesim = {
        sid: d.sprint for d in plan.dilimler for sid in d.story_idler
    }
    # US2 önceliği daha yüksek olmasına RAĞMEN US1'den önceki bir sprinte düşemez.
    assert yerlesim["US2"] >= yerlesim["US1"]


def test_ayni_girdi_ayni_plani_uretir():
    storyler = [_story(f"US{i}", (i % 3) + 1, oncelik=(i % 5) + 1) for i in range(1, 10)]
    kapasite = Kapasite(ekip_buyuklugu=3, sprint_sayisi=3)
    assert sprint_dagit(storyler, kapasite) == sprint_dagit(storyler, kapasite)


def test_hicbir_story_sessizce_dusmez():
    """Bütçeye sığmayan story plandan ATILMAZ — yerleştirilir ve RAPORLANIR."""
    storyler = [_story("US1", 13), _story("US2", 1), _story("US3", 1)]
    plan = sprint_dagit(storyler, Kapasite(ekip_buyuklugu=2, sprint_sayisi=3))
    yerlesenler = {sid for d in plan.dilimler for sid in d.story_idler}
    assert yerlesenler == {"US1", "US2", "US3"}
    assert any("US1" in u for u in plan.uyarilar)


def test_dongu_askida_birakmaz_uyari_verir():
    storyler = [
        _story("US1", 2, bagimliliklar=["US2"]),
        _story("US2", 2, bagimliliklar=["US1"]),
    ]
    plan = sprint_dagit(storyler, Kapasite(ekip_buyuklugu=2, sprint_sayisi=2))
    yerlesenler = {sid for d in plan.dilimler for sid in d.story_idler}
    assert yerlesenler == {"US1", "US2"}
    assert any("döngü" in u.lower() for u in plan.uyarilar)


def test_bos_backlog_sessiz_kalmaz():
    plan = sprint_dagit([], Kapasite(ekip_buyuklugu=3, sprint_sayisi=2))
    assert plan.toplam_puan == 0
    assert plan.uyarilar != []


def test_sifir_musaitlik_reddedilir():
    """Sıfır kapasiteli sprint sessizce kabul edilseydi plan sessizce bozulurdu."""
    with pytest.raises(ValidationError):
        Kapasite(ekip_buyuklugu=3, sprint_sayisi=2, musaitlik=[1.0, 0.0])


def test_musaitlik_uzunlugu_sprint_sayisiyla_uyusmali():
    kapasite = Kapasite(ekip_buyuklugu=3, sprint_sayisi=3, musaitlik=[1.0, 1.0])
    with pytest.raises(ValueError):
        kapasite.agirliklar()


def test_kapasite_eksik_kisittan_uydurulmaz():
    assert kapasite_briefden(None, 3) is None
    assert kapasite_briefden(4, None) is None
    assert kapasite_briefden(4, 3) == Kapasite(ekip_buyuklugu=4, sprint_sayisi=3)
