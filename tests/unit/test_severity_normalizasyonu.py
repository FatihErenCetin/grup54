"""#327 — judge'in yazdigi severity metni kanonik dagarciğa cevrilmeli.

OLCULEN HATA (uretim, 2026-07-29): judge `"High"` donduruyordu, `Detection.
severity` ise `Literal["low","med","high"]` bekliyor. Pydantic reddedince
`JudgeUnavailableError` firlatiliyor; UC ardisik boyle hata devre kesiciyi
aciyor ve kalan cifTLER hic DENENMEDEN dusuyor. Uretim bilancosu:

    degraded: {"judge_unavailable": 1509, "evaluated": 11}

1520 adayin 1509'u — yani tespit kapasitesinin ~%99'u — tek bir harf
buyuklugu farki yuzunden kayboldu. Sistem YANLIS davranmadi (yargiyi
uydurmadi, #252 sozlesmesi); ama hatanin dogru ele alinmasi, hatanin
olmamasindan ucuz degil.

Bu testler iki AYRI seyi kilitler ve ikisi de ayni derecede onemli:
  1. Yazim/es-anlam farklari KABUL EDILIR   (kapasite kaybi olmasin)
  2. Bilinmeyen deger VARSAYILANA DUSMEZ    (fail-open geri gelmesin)
"""

import pytest

from ensemble.models import Detection, severity_normalize


@pytest.mark.parametrize(
    "ham,beklenen",
    [
        ("High", "high"),  # <-- uretimde gorulen GERCEK deger
        ("HIGH", "high"),
        ("high", "high"),
        ("  high  ", "high"),
        ("Medium", "med"),  # modelin dogal kelimesi; bizim kisaltmamiz "med"
        ("medium", "med"),
        ("med", "med"),
        ("Low", "low"),
        ("low", "low"),
    ],
)
def test_yazim_farklari_kabul_edilir(ham: str, beklenen: str):
    """MUTASYON KILIDI: `severity_normalize`'daki `.strip().lower()`i kaldir
    -> "High"/"HIGH"/"  high  "/"Medium" satirlari kirmizi olur."""
    assert severity_normalize(ham) == beklenen


@pytest.mark.parametrize("ham", ["kritik", "severe", "urgent", "", "   ", "hgh", "1"])
def test_bilinmeyen_deger_UYDURULMAZ(ham: str):
    """Bilinmeyen severity `ValueError` firlatir — varsayilana DUSMEZ.

    Bu, testin en onemli yari. `low` dondurmek cazip gorunur ("hic yoktan
    iyidir") ama #252'de bilerek kaldirilan `_fallback_detection` fail-open'in
    ta kendisidir: degerlendirilememis bir cift, degerlendirilmis ve zararsiz
    bulunmus gibi gorunur; radar "temiz" der ve neden temiz oldugunu kimse
    bilemez.

    MUTASYON KILIDI: `raise ValueError` yerine `return "low"` yaz -> bu test
    kirmizi olur.
    """
    with pytest.raises(ValueError):
        severity_normalize(ham)


def test_normalize_edilmis_deger_Detection_kurar():
    """Normalizasyonun ISE YARADIGINI ucundan ucuna gosterir: ham "High" ile
    dogrudan Detection kurmak PATLAR, normalize edilmisi kurar.

    Iki iddia birlikte anlamli — yalniz ikincisi yazilsaydi, normalizasyon
    kaldirildiginda bile test yesil kalabilirdi (cunku "high" zaten gecerli).
    """
    ortak = {
        "id": "a-b",
        "actors": ["esma6", "FatihErenCetin"],
        "branches": ["main"],
        "files": ["src/backend/ensemble/app.py"],
        "confidence": 0.7,
        "rationale": "ayni dosyada cakisan degisiklik",
    }
    # HAM deger: uretimde tam olarak bu patliyordu
    with pytest.raises(ValueError):
        Detection(severity="High", **ortak)

    # NORMALIZE edilmis: gecer
    tespit = Detection(severity=severity_normalize("High"), **ortak)
    assert tespit.severity == "high"
