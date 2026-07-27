"""#288 — judge devre kesici.

Ölçülen sorun (canlı, 2026-07-27): Gemini ücretsiz katmanı `generate_content`
için GÜNDE 20 istek veriyor. Tükendikten sonra `/radar` her adayı yine
deniyordu — 3 dakikada 392 kota hatası, `/radar` 35 saniye, sonuç yine
"iki sağlayıcı da değerlendiremedi".
"""

import pytest

from ensemble.engine.devre_kesici import DevreKesiciJudge
from ensemble.engine.fallback import FallbackJudge
from ensemble.models import Detection, NormalizedEvent
from ensemble.ports import JudgeUnavailableError


def _olay(id_: str) -> NormalizedEvent:
    from datetime import datetime

    return NormalizedEvent(
        id=id_, type="commit", actor="esma", branch=None, files=["a.py"],
        ts=datetime(2026, 7, 27, 9, 0, 0), ref=id_,
    )


def _tespit() -> Detection:
    return Detection(
        id="d1", kind="conflict", actors=["esma", "enes"], branches=["main"],
        files=["a.py"], severity="low", confidence=0.5, rationale="test",
    )


class _Sayan:
    """Çağrı sayan sahte judge; `hep_hata` ile davranışı seçilir."""

    def __init__(self, hep_hata: bool = False):
        self.cagri = 0
        self.hep_hata = hep_hata

    def judge_conflict(self, a, b, overlap, sim):
        self.cagri += 1
        if self.hep_hata:
            raise JudgeUnavailableError("kota bitti")
        return _tespit()


class _Saat:
    def __init__(self):
        self.simdi = 0.0

    def __call__(self):
        return self.simdi

    def ilerle(self, sn: float):
        self.simdi += sn


def _cagir(judge, n: int) -> int:
    """n kez çağır, kaç tanesi JudgeUnavailableError verdi say."""
    hata = 0
    for i in range(n):
        try:
            judge.judge_conflict(_olay(f"a{i}"), _olay(f"b{i}"), ["a.py"], 0.9)
        except JudgeUnavailableError:
            hata += 1
    return hata


def test_esik_sonrasi_SAGLAYICIYA_GITMEZ():
    """Asıl kazanç: 3 hatadan sonra sağlayıcı bir daha aranmaz.

    MUTASYON KİLİDİ: devre kesici kaldırılırsa 100 çağrının 100'ü de
    sağlayıcıya gider (canlıda ölçülen 392 kota hatasının sebebi).
    """
    ic = _Sayan(hep_hata=True)
    judge = DevreKesiciJudge(ic, esik=3, soguma_s=60.0, saat=_Saat())

    hata = _cagir(judge, 100)

    assert hata == 100, "hepsi başarısız olmalı (yargı UYDURULMUYOR)"
    assert ic.cagri == 3, f"sağlayıcı yalnız eşik kadar aranmalı, {ic.cagri} kez arandı"
    assert judge.kesilen == 97


def test_devre_acikken_de_YARGI_UYDURMAZ():
    """Devre kesici hızlandırır, SUSTURMAZ.

    "bu çift çakışma DEĞİL" ile "bu çifti değerlendiremedik" farkı bu repoda
    pahalıya öğrenildi (bkz. `JudgeUnavailableError` docstring'i). Devre açıkken
    düşük-güvenli bir Detection dönmek, tam da o hatanın tekrarı olurdu.
    """
    judge = DevreKesiciJudge(_Sayan(hep_hata=True), esik=1, soguma_s=60.0, saat=_Saat())

    _cagir(judge, 1)  # esik=1 -> bu cagri devreyi acar
    with pytest.raises(JudgeUnavailableError) as ctx:
        judge.judge_conflict(_olay("x"), _olay("y"), [], None)

    assert "UYDURULMADI" in str(ctx.value)


def test_soguma_dolunca_YENIDEN_dener():
    saat = _Saat()
    ic = _Sayan(hep_hata=True)
    judge = DevreKesiciJudge(ic, esik=2, soguma_s=60.0, saat=saat)

    _cagir(judge, 10)
    assert ic.cagri == 2, "devre açıldıktan sonra aranmamalı"

    saat.ilerle(61)
    _cagir(judge, 10)
    assert ic.cagri == 3, "soğuma sonrası TEK bir yoklama yapılmalı, sonra yine kesilmeli"


def test_basari_sayaci_SIFIRLAR():
    """'Ardışık' kelimesinin anlamı: gün boyunca dağınık tekil hatalar devreyi
    açmamalı — yalnız üst üste gelenler."""
    saat = _Saat()

    class _AralikliHata:
        def __init__(self):
            self.cagri = 0

        def judge_conflict(self, a, b, overlap, sim):
            self.cagri += 1
            if self.cagri % 2 == 1:  # bir hata, bir başarı
                raise JudgeUnavailableError("geçici")
            return _tespit()

    ic = _AralikliHata()
    judge = DevreKesiciJudge(ic, esik=3, soguma_s=60.0, saat=saat)

    _cagir(judge, 20)
    assert ic.cagri == 20, "dağınık hatalarda devre AÇILMAMALI"
    assert judge.kesilen == 0


def test_devre_kesici_YEDEGI_kesmez():
    """Kritik sarma kararı: her sağlayıcı KENDİ kesicisiyle sarılır.

    Tek bir kesici `FallbackJudge`'ı dıştan sarsaydı, Gemini'nin günlük kotası
    bitince ÇALIŞAN Groq'a gitmeyi de keserdi — yedeğin varlık sebebi tam da
    o an. MUTASYON KİLİDİ: `app.py` sarmayı dışarı taşırsa bu senaryo kırılır.
    """
    olu = _Sayan(hep_hata=True)      # Gemini: kota bitmiş
    calisan = _Sayan(hep_hata=False)  # Groq: sağlam

    judge = FallbackJudge(
        primary=DevreKesiciJudge(olu, esik=2, soguma_s=60.0, saat=_Saat()),
        secondary=DevreKesiciJudge(calisan, esik=2, soguma_s=60.0, saat=_Saat()),
    )

    hata = _cagir(judge, 10)

    assert hata == 0, "yedek sağlam: hiçbir çağrı başarısız olmamalı"
    assert olu.cagri == 2, "ölü sağlayıcı kesilmeli"
    assert calisan.cagri == 10, "çalışan yedek KESİLMEMELİ — 10 çağrının hepsi ona gitmeli"


def test_esik_sifir_reddedilir():
    with pytest.raises(ValueError):
        DevreKesiciJudge(_Sayan(), esik=0)
