"""Taslak sağlayıcısı: yedeğe geçiş + "sessizce boş taslak üretme" (#340).

Kota gerçeği (ölçüldü 2026-07-27, `gemini/client.py::_bekleme`): ücretsiz
`generate_content` kotası **20 istek/GÜN**. Sihirbaz demo sırasında bu duvara
toslarsa iki kabul edilebilir davranış var — yedeğe geçmek ya da durumu BEYAN
etmek. Kabul EDİLEMEZ olan üçüncüsü: boş bir taslağı başarı gibi akıtmak.
"""

import pytest

from ensemble.config import Settings
from ensemble.onboarding.drafter import (
    FallbackOnboardingDrafter,
    GeminiOnboardingDrafter,
    GroqOnboardingDrafter,
    OllamaOnboardingDrafter,
    TaslakUretilemedi,
    build_drafter,
)
from ensemble.onboarding.intake import Brief

_GECERLI_BRIEF_JSON = (
    '{"urun_tek_cumle":"Ekipler icin ortak proje beyni.",'
    '"hedef_kullanicilar":["gelistirici"],'
    '"cekirdek_ozellikler":["radar","board","scope"],'
    '"kapsam_disi":["mobil"],'
    '"kisit_ekip_buyuklugu":4,"kisit_sprint_sayisi":3,"kisit_sprint_gun":14,'
    '"kisit_yetkinlikler":["python"],"kisit_teknolojiler":["FastAPI"],'
    '"kisit_entegrasyonlar":["GitHub"],'
    '"basari_hedefi":"Canli demoda cakisma radarda gorunsun.",'
    '"varsayimlar":[{"alan":"kapsam_disi","deger_ozeti":"mobil yok",'
    '"gerekce":"metinde gecmiyor"}]}'
)

_GECERLI_TASLAK_JSON = (
    '{"epicler":[{"id":"E1","baslik":"Radar","aciklama":"cakisma tespiti"}],'
    '"storyler":[{"id":"US1","epic_id":"E1","rol":"gelistirici",'
    '"istek":"cakismalari gormek","fayda":"erken fark edeyim",'
    '"kabul_kriterleri":["kart gorunur"],"puan":5,"oncelik":1,'
    '"bagimliliklar":[]}]}'
)


class _SahteIstemci:
    """`generate_content(prompt, response_schema=...)` imzasını taşıyan stub."""

    def __init__(self, cevaplar: list[str | Exception]) -> None:
        self.cevaplar = list(cevaplar)
        self.cagri_sayisi = 0

    def generate_content(self, prompt: str, *, response_schema=None) -> str:
        self.cagri_sayisi += 1
        cevap = self.cevaplar.pop(0)
        if isinstance(cevap, Exception):
            raise cevap
        return cevap


def _settings(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


def test_gecerli_yanit_briefe_cevrilir():
    drafter = GeminiOnboardingDrafter(
        _settings(GEMINI_API_KEY="k"), client=_SahteIstemci([_GECERLI_BRIEF_JSON])
    )
    brief = drafter.brief_uret(
        serbest_metin="metin", mevcut=Brief(), varsayimlarla_doldur=True
    )
    assert brief.cekirdek_ozellikler == ["radar", "board", "scope"]
    assert brief.kisitlar.ekip_buyuklugu == 4
    assert [v.alan for v in brief.varsayimlar] == ["kapsam_disi"]


def test_sifir_sayilar_none_olur_uydurulmaz():
    """Model "bilmiyorum" derse (0), alan `None` kalır — 0 kişilik ekip YAZILMAZ."""
    ham = _GECERLI_BRIEF_JSON.replace('"kisit_ekip_buyuklugu":4', '"kisit_ekip_buyuklugu":0')
    drafter = GroqOnboardingDrafter(_settings(GROQ_API_KEY="k"), client=_SahteIstemci([ham]))
    brief = drafter.brief_uret(serbest_metin="x", mevcut=Brief(), varsayimlarla_doldur=False)
    assert brief.kisitlar.ekip_buyuklugu is None


def test_dogrulanamayan_yanit_taslak_uretmez():
    """Şemaya uymayan yanıt = yanıt YOK. Kısmi parse edip uydurmuyoruz."""
    drafter = GeminiOnboardingDrafter(
        _settings(GEMINI_API_KEY="k"), client=_SahteIstemci(['{"bozuk": true}'])
    )
    with pytest.raises(TaslakUretilemedi):
        drafter.brief_uret(serbest_metin="x", mevcut=Brief(), varsayimlarla_doldur=False)


def test_bos_story_listesi_basari_sayilmaz():
    """Sessizce boş taslak YASAK — model hiç story üretmediyse bu bir hatadır."""
    drafter = GeminiOnboardingDrafter(
        _settings(GEMINI_API_KEY="k"),
        client=_SahteIstemci(['{"epicler":[],"storyler":[]}']),
    )
    with pytest.raises(TaslakUretilemedi):
        drafter.story_uret(Brief())


def test_yedek_birincil_dusunce_devralir():
    birincil = GeminiOnboardingDrafter(
        _settings(GEMINI_API_KEY="k"),
        client=_SahteIstemci([RuntimeError("429 kota bitti")]),
    )
    yedek_istemci = _SahteIstemci([_GECERLI_TASLAK_JSON])
    yedek = GroqOnboardingDrafter(_settings(GROQ_API_KEY="g"), client=yedek_istemci)

    taslak = FallbackOnboardingDrafter(primary=birincil, secondary=yedek).story_uret(Brief())

    assert [s.id for s in taslak.storyler] == ["US1"]
    assert yedek_istemci.cagri_sayisi == 1


def test_iki_saglayici_da_dusunce_hata_yayilir():
    """Fail-open YASAK: iki sağlayıcı da düşerse sahte taslak ÜRETİLMEZ."""
    birincil = GeminiOnboardingDrafter(
        _settings(GEMINI_API_KEY="k"), client=_SahteIstemci([RuntimeError("kota")])
    )
    yedek = GroqOnboardingDrafter(
        _settings(GROQ_API_KEY="g"), client=_SahteIstemci([RuntimeError("429")])
    )
    with pytest.raises(TaslakUretilemedi) as hata:
        FallbackOnboardingDrafter(primary=birincil, secondary=yedek).story_uret(Brief())
    # İki hata da mesajda görünür — "hangisi neden düştü" cevaplanabilsin.
    assert "birincil" in str(hata.value) and "yedek" in str(hata.value)


def test_saglayici_yoksa_sahte_drafter_kurulmaz():
    """`build_drafter` uydurma bir Fake DÖNDÜRMEZ — `None` döner, uç beyan eder."""
    assert build_drafter(_settings(GEMINI_API_KEY=None, GROQ_API_KEY="")) is None


def test_gemini_plus_groq_yedekli_kurulur():
    drafter = build_drafter(_settings(GEMINI_API_KEY="k", GROQ_API_KEY="g"))
    assert isinstance(drafter, FallbackOnboardingDrafter)


def test_yerel_kal_modunda_bulut_yedegi_devreye_girmez():
    """README'nin 'tam-yerel gizlilik modu' taahhüdü: prompt kullanıcının ürün
    metnini taşır, `LLM_PROVIDER=ollama` iken buluta GİTMEZ (#255 dersi)."""
    drafter = build_drafter(
        _settings(LLM_PROVIDER="ollama", GEMINI_API_KEY="k", GROQ_API_KEY="g")
    )
    assert isinstance(drafter, OllamaOnboardingDrafter)
