"""Onboarding'in TEK LLM yüzeyi (#340, §8.5) — port + sağlayıcı + yedek.

İki iş yapar, ikisi de birer TASLAK üretir (K6: AI taslaklar, insan onaylar):

  1. `brief_uret`  — serbest metinden sabit şemayı çıkarır; kullanıcı "bununla
     devam et" derse boşlukları makul varsayımlarla doldurur ve **varsayımları
     işaretler**.
  2. `story_uret`  — brief'ten epic + user story + kabul kriteri + puan taslağı.

Çağrı bütçesi: sihirbazın TAMAMI için en çok 2 LLM çağrısı (tur başına 1).
Soru üretimi, boşluk tespiti ve sprint dağıtımı bilerek deterministik kodda
(`intake.py`, `sprint_plan.py`) — ölçülen kota 20 istek/GÜN (bkz.
`integrations/gemini/client.py::_bekleme` docstring'i, 2026-07-27 ölçümü).

Fail-open YASAK: sağlayıcı düşerse bu modül **hiçbir şey uydurmaz**,
`TaslakUretilemedi` fırlatır. Çağıran (router) bunu bir DEĞERE değil, cevabın
`degraded` alanına çevirir — `RadarResponse.degraded`/#252 deseninin
onboarding'deki birebir karşılığı. "Boş taslak döndürüp başarı gibi akıtmak"
tam olarak o desenin yasakladığı şeydir.
"""

from __future__ import annotations

import json
import logging
from typing import Protocol

from pydantic import BaseModel, ValidationError

from ensemble.config import Settings
from ensemble.integrations.gemini.client import ResilientGeminiClient
from ensemble.integrations.gemini.errors import GeminiPermanentError, GeminiTransientError
from ensemble.integrations.groq.client import GroqClient
from ensemble.integrations.groq.errors import GroqError
from ensemble.integrations.ollama.client import OllamaClient
from ensemble.integrations.ollama.errors import OllamaError
from ensemble.onboarding.intake import (
    Brief,
    Kisitlar,
    Varsayim,
    alan_adi,
    eksik_alanlar,
)
from ensemble.onboarding.story import Epic, StoryTaslagi, UserStory

logger = logging.getLogger("ensemble.onboarding.drafter")


class TaslakUretilemedi(RuntimeError):
    """Sağlayıcı bu taslağı ÜRETEMEDİ (kota, ağ, doğrulanamayan yanıt).

    `JudgeUnavailableError` ile aynı sözleşme: hata bir DEĞERE dönüştürülmez.
    "Model boş brief döndürdü" ile "modele ulaşılamadı" ayrı olgulardır; tek
    nesneye sıkıştırılırsa kullanıcı ekranda boş bir taslak görür ve onu
    ürünün cevabı sanır. Çağıranın görevi: yakala, BEYAN ET (`degraded`).
    """


# --- LLM yanıt şemaları --------------------------------------------------
#
# Neden `Brief`/`StoryTaslagi`'nı doğrudan `response_schema` yapmıyoruz:
# yapılandırılmış çıktı `int | None` gibi birleşim (anyOf) tiplerinde
# sağlayıcıdan sağlayıcıya farklı davranıyor (Groq şemayı ZORLAMIYOR bile —
# bkz. `groq/client.py` başlığı). Bu yüzden yanıt şemaları BİLEREK düz:
# opsiyonel sayılar `0` = "bilinmiyor" olarak taşınır ve dönüşümde `None`
# olur. Tek bir sağlayıcıya göre şekillenmiş bir şema, yedeğe düşüldüğünde
# sessizce bozulurdu.


class _VarsayimYaniti(BaseModel):
    alan: str
    deger_ozeti: str
    gerekce: str


class _BriefYaniti(BaseModel):
    urun_tek_cumle: str
    hedef_kullanicilar: list[str]
    cekirdek_ozellikler: list[str]
    kapsam_disi: list[str]
    kisit_ekip_buyuklugu: int
    kisit_sprint_sayisi: int
    kisit_sprint_gun: int
    kisit_yetkinlikler: list[str]
    kisit_teknolojiler: list[str]
    kisit_entegrasyonlar: list[str]
    basari_hedefi: str
    varsayimlar: list[_VarsayimYaniti]


class _EpicYaniti(BaseModel):
    id: str
    baslik: str
    aciklama: str


class _StoryYaniti(BaseModel):
    id: str
    epic_id: str
    rol: str
    istek: str
    fayda: str
    kabul_kriterleri: list[str]
    puan: int
    oncelik: int
    bagimliliklar: list[str]


class _TaslakYaniti(BaseModel):
    epicler: list[_EpicYaniti]
    storyler: list[_StoryYaniti]


def _pozitif_ya_da_none(deger: int) -> int | None:
    return deger if deger > 0 else None


def _yaniti_briefe_cevir(yanit: _BriefYaniti) -> Brief:
    return Brief(
        urun_tek_cumle=yanit.urun_tek_cumle.strip(),
        hedef_kullanicilar=[x.strip() for x in yanit.hedef_kullanicilar if x.strip()],
        cekirdek_ozellikler=[x.strip() for x in yanit.cekirdek_ozellikler if x.strip()],
        kapsam_disi=[x.strip() for x in yanit.kapsam_disi if x.strip()],
        kisitlar=Kisitlar(
            ekip_buyuklugu=_pozitif_ya_da_none(yanit.kisit_ekip_buyuklugu),
            sprint_sayisi=_pozitif_ya_da_none(yanit.kisit_sprint_sayisi),
            sprint_gun=_pozitif_ya_da_none(yanit.kisit_sprint_gun),
            yetkinlikler=[x.strip() for x in yanit.kisit_yetkinlikler if x.strip()],
            teknolojiler=[x.strip() for x in yanit.kisit_teknolojiler if x.strip()],
            entegrasyonlar=[x.strip() for x in yanit.kisit_entegrasyonlar if x.strip()],
        ),
        basari_hedefi=yanit.basari_hedefi.strip(),
        varsayimlar=[
            Varsayim(alan=v.alan, deger_ozeti=v.deger_ozeti, gerekce=v.gerekce)
            for v in yanit.varsayimlar
        ],
    )


def _yaniti_taslaga_cevir(yanit: _TaslakYaniti) -> StoryTaslagi:
    return StoryTaslagi(
        epicler=[Epic(id=e.id, baslik=e.baslik, aciklama=e.aciklama) for e in yanit.epicler],
        storyler=[
            UserStory(
                id=s.id,
                epic_id=s.epic_id,
                rol=s.rol,
                istek=s.istek,
                fayda=s.fayda,
                kabul_kriterleri=[k for k in s.kabul_kriterleri if k.strip()],
                puan=s.puan,
                oncelik=s.oncelik,
                bagimliliklar=s.bagimliliklar,
            )
            for s in yanit.storyler
        ],
    )


# --- Prompt'lar ----------------------------------------------------------
#
# İki sağlayıcı AYNI prompt'u kullanır (`gemini/judge.py` <-> `groq/judge.py`
# `_build_prompt` paylaşımının aynı gerekçesi): yedeğe düşüldüğünde ölçüt
# değişmesin. Kopyalanan prompt zamanla iki farklı ürün davranışına ayrışır.

_UYDURMA_YASAGI = (
    "KURAL: Metinde OLMAYAN bilgiyi UYDURMA. Bilmediğin metin alanını boş "
    'string (""), bilmediğin listeyi boş liste ([]), bilmediğin sayıyı 0 '
    "olarak bırak. Eksik bırakmak, yanlış doldurmaktan iyidir."
)


def _brief_prompt(*, serbest_metin: str, mevcut: Brief, varsayimlarla_doldur: bool) -> str:
    eksikler = eksik_alanlar(mevcut)
    eksik_metni = (
        ", ".join(f"{alan_adi(e.alan)} ({e.neden})" for e in eksikler) or "yok"
    )
    if varsayimlarla_doldur:
        varsayim_kurali = (
            "Kullanıcı 'bununla devam et' dedi. YALNIZCA yukarıda eksik olarak "
            "listelenen alanları, metinden ve alanın kendi bağlamından çıkan MAKUL "
            "varsayımlarla doldur. Doldurduğun HER alan için `varsayimlar` listesine "
            "bir kayıt ekle (alan = alan id'si, deger_ozeti = ne yazdığın, gerekce = "
            "neden böyle varsaydığın). Kullanıcının KENDİ verdiği alanlar için "
            "varsayım kaydı EKLEME."
        )
    else:
        varsayim_kurali = (
            "Kullanıcı varsayım İSTEMEDİ. Metinde açıkça olmayan hiçbir alanı doldurma; "
            "`varsayimlar` listesini boş bırak."
        )

    return (
        "Sen bir ürün sahibi asistanısın. Aşağıdaki serbest metinden bir proje "
        "brief'i çıkar ve SABİT şemayı doldur. Türkçe yaz.\n\n"
        f"{_UYDURMA_YASAGI}\n\n"
        "Alan anlamları:\n"
        "- urun_tek_cumle: ne / kime / hangi problem (TEK cümle)\n"
        "- hedef_kullanicilar: rol adları (kısa)\n"
        "- cekirdek_ozellikler: MVP kapsamı, 3-7 madde\n"
        "- kapsam_disi: bilinçli yapılmayacaklar\n"
        "- kisit_*: ekip büyüklüğü, sprint sayısı, sprint gün sayısı, yetkinlikler, "
        "teknolojiler, entegrasyonlar (sayılar bilinmiyorsa 0)\n"
        "- basari_hedefi: neyi gösterirse 'oldu' denecek\n\n"
        f"Şu an eksik olan alanlar: {eksik_metni}\n"
        f"{varsayim_kurali}\n\n"
        "Halihazırda toplanmış brief (JSON, boş alanlar doldurulmamış demektir):\n"
        f"{mevcut.model_dump_json(indent=None)}\n\n"
        "Kullanıcının serbest metni:\n"
        f"{serbest_metin.strip() or '(boş)'}\n"
    )


def _story_prompt(brief: Brief) -> str:
    return (
        "Aşağıdaki proje brief'inden bir SPRINT BACKLOG TASLAĞI üret. Türkçe yaz.\n\n"
        "Üret:\n"
        "- epicler: 2-5 epic (id 'E1','E2'... biçiminde)\n"
        "- storyler: her epic altında user story'ler (id 'US1','US2'... biçiminde)\n"
        "  * rol / istek / fayda ALANLARI AYRI doldurulur; cümle şu kalıba "
        "oturmalı: 'Bir <rol> olarak <istek> istiyorum, böylece <fayda>.'\n"
        "    - rol: brief'teki hedef kullanıcılardan biri\n"
        "    - istek: '...' (mastar/istek kipi, 'istiyorum' KELİMESİNİ YAZMA)\n"
        "    - fayda: 'böylece'den sonra gelecek kısım\n"
        "  * kabul_kriterleri: 2-4 madde, GÖZLENEBİLİR olsun (ölçülebilir/tıklanabilir)\n"
        "  * puan: yalnız 1, 2, 3, 5, 8, 13 değerlerinden biri (planning poker)\n"
        "  * oncelik: 1 (en yüksek) - 5 (en düşük)\n"
        "  * bagimliliklar: yalnız BU taslakta var olan story id'leri; yoksa []\n\n"
        "KURAL: Yalnızca brief'teki çekirdek özelliklerden story üret. Brief'te "
        "olmayan bir özellik icat etme; kapsam dışı listesindeki hiçbir şey için "
        "story YAZMA.\n\n"
        f"Brief (JSON):\n{brief.model_dump_json(indent=None)}\n"
    )


# --- Port + sağlayıcılar --------------------------------------------------


class OnboardingDrafterPort(Protocol):
    def brief_uret(
        self, *, serbest_metin: str, mevcut: Brief, varsayimlarla_doldur: bool
    ) -> Brief: ...

    def story_uret(self, brief: Brief) -> StoryTaslagi: ...


class _MetinUreticiDrafter:
    """`generate_content(prompt, response_schema=...)` sunan her istemcinin
    ortak gövdesi — Gemini/Groq/Ollama üçü de bu imzayı taşıyor.

    Sağlayıcıya özgü tek şey hata sınıfıdır; alt sınıflar onu bildirir.
    """

    _hata_tipleri: tuple[type[Exception], ...] = ()
    ad = "?"

    def _uret(self, prompt: str, sema: type[BaseModel]) -> str:  # pragma: no cover - alt sınıf
        raise NotImplementedError

    def _cagir(self, prompt: str, sema: type[BaseModel]) -> BaseModel:
        try:
            ham = self._uret(prompt, sema)
        except self._hata_tipleri as exc:
            raise TaslakUretilemedi(f"{self.ad}: {exc}") from exc
        except Exception as exc:  # ağ/SDK dışı beklenmedik durumlar
            raise TaslakUretilemedi(f"{self.ad}: beklenmeyen hata — {exc}") from exc
        try:
            return sema.model_validate_json(ham)
        except (ValidationError, ValueError) as exc:
            # Doğrulanamayan yanıt = yanıt YOK. Kısmen parse edip kalanı
            # varsayılanla doldurmak, modelin söylemediği şeyi söylemiş gibi
            # göstermek olurdu.
            raise TaslakUretilemedi(f"{self.ad}: yanıt şemaya uymadı — {exc}") from exc

    def brief_uret(
        self, *, serbest_metin: str, mevcut: Brief, varsayimlarla_doldur: bool
    ) -> Brief:
        prompt = _brief_prompt(
            serbest_metin=serbest_metin,
            mevcut=mevcut,
            varsayimlarla_doldur=varsayimlarla_doldur,
        )
        yanit = self._cagir(prompt, _BriefYaniti)
        assert isinstance(yanit, _BriefYaniti)
        return _yaniti_briefe_cevir(yanit)

    def story_uret(self, brief: Brief) -> StoryTaslagi:
        yanit = self._cagir(_story_prompt(brief), _TaslakYaniti)
        assert isinstance(yanit, _TaslakYaniti)
        taslak = _yaniti_taslaga_cevir(yanit)
        if not taslak.storyler:
            # Boş taslak "başarı" değildir: kullanıcı ekranda hiçbir şey görür
            # ve bunu ürünün cevabı sanar. Beyan edilmiş bir başarısızlık,
            # sessiz bir boşluktan iyidir (#252).
            raise TaslakUretilemedi(f"{self.ad}: model hiç story üretmedi")
        return taslak


class GeminiOnboardingDrafter(_MetinUreticiDrafter):
    ad = "gemini"
    _hata_tipleri = (GeminiTransientError, GeminiPermanentError)

    def __init__(self, settings: Settings, client: ResilientGeminiClient | None = None) -> None:
        self._settings = settings
        self._client = client

    def _uret(self, prompt: str, sema: type[BaseModel]) -> str:
        client = self._client or ResilientGeminiClient(self._settings)
        return client.generate_content(prompt, response_schema=sema)


class GroqOnboardingDrafter(_MetinUreticiDrafter):
    ad = "groq"
    _hata_tipleri = (GroqError,)

    def __init__(self, settings: Settings, client: GroqClient | None = None) -> None:
        self._settings = settings
        self._client = client

    def _uret(self, prompt: str, sema: type[BaseModel]) -> str:
        client = self._client or GroqClient(self._settings)
        return client.generate_content(prompt, response_schema=sema)


class OllamaOnboardingDrafter(_MetinUreticiDrafter):
    ad = "ollama"
    _hata_tipleri = (OllamaError,)

    def __init__(self, settings: Settings, client: OllamaClient | None = None) -> None:
        self._settings = settings
        self._client = client

    def _uret(self, prompt: str, sema: type[BaseModel]) -> str:
        client = self._client or OllamaClient(self._settings)
        return client.generate_content(prompt, response_schema=sema)


class FallbackOnboardingDrafter:
    """Birincil düşerse ikincili dener — `engine/fallback.FallbackJudge` deseni.

    Neden burada da gerekli: ölçülen Gemini ücretsiz kotası **20 istek/GÜN**.
    Sihirbaz jüri demosu sırasında o duvara toslarsa ekranda hiçbir taslak
    olmaz. Yedek sağlayıcının kotası ayrıdır; "biraz farklı üsluplu bir taslak"
    ile "hiç taslak yok" arasında seçim yapıyoruz — iki tutarlı taslak
    arasında değil.

    İKİSİ de düşerse `TaslakUretilemedi` yayılır; sahte taslak ÜRETİLMEZ.
    """

    ad = "fallback"

    def __init__(self, primary: OnboardingDrafterPort, secondary: OnboardingDrafterPort) -> None:
        self.primary = primary
        self.secondary = secondary

    def brief_uret(
        self, *, serbest_metin: str, mevcut: Brief, varsayimlarla_doldur: bool
    ) -> Brief:
        return self._dene(
            lambda d: d.brief_uret(
                serbest_metin=serbest_metin,
                mevcut=mevcut,
                varsayimlarla_doldur=varsayimlarla_doldur,
            )
        )

    def story_uret(self, brief: Brief) -> StoryTaslagi:
        return self._dene(lambda d: d.story_uret(brief))

    def _dene(self, is_fn):
        try:
            return is_fn(self.primary)
        except TaslakUretilemedi as birincil:
            logger.info("birincil taslak sağlayıcısı düştü, yedeğe geçiliyor: %s", birincil)
            try:
                return is_fn(self.secondary)
            except TaslakUretilemedi as ikincil:
                raise TaslakUretilemedi(
                    f"iki sağlayıcı da taslak üretemedi (birincil: {birincil} · "
                    f"yedek: {ikincil})"
                ) from birincil


def build_drafter(settings: Settings) -> OnboardingDrafterPort | None:
    """Yapılandırmaya göre taslak sağlayıcısını kurar; hiçbiri yoksa `None`.

    `None` BİLİNÇLİ — burada bir `FakeOnboardingDrafter` YOK. `FakeJudgeAdapter`
    /`FakeScopeDrafter` var çünkü onların ürettiği şey ya kural-tabanlı bir
    yargı ya da "[TASLAK] PO doldursun" gibi kendini ele veren bir iskelettir.
    Bir onboarding brief'i/story listesi ise kullanıcının kendi projesi
    hakkında CÜMLELER içerir; sahte bir tanesi ekranda gerçekten üretilmiş
    gibi görünür. Sağlayıcı yoksa doğru cevap "sağlayıcı yok" demektir
    (`/onboarding/durum` bunu ÖNCEDEN söyler, kullanıcı boşuna tıklamasın).

    Yerel-kal modu korunur: `LLM_PROVIDER=ollama` iken Groq yedeği DEVREYE
    GİRMEZ — prompt kullanıcının ürün metnini taşır ve buluta gönderilmesi
    README'nin "tam-yerel gizlilik modu" taahhüdünü bozardı (#255'te judge
    için verilen kararın aynısı, dahil-etme listesiyle).
    """
    if settings.LLM_PROVIDER == "ollama":
        return OllamaOnboardingDrafter(settings)
    if not settings.GEMINI_API_KEY:
        if settings.GROQ_API_KEY:
            return GroqOnboardingDrafter(settings)
        return None
    birincil: OnboardingDrafterPort = GeminiOnboardingDrafter(settings)
    if settings.GROQ_API_KEY:
        return FallbackOnboardingDrafter(
            primary=birincil, secondary=GroqOnboardingDrafter(settings)
        )
    return birincil


def saglayici_adi(settings: Settings) -> str:
    """`/onboarding/durum` için okunur sağlayıcı etiketi (uydurma yok)."""
    if settings.LLM_PROVIDER == "ollama":
        return f"ollama:{settings.OLLAMA_MODEL}"
    parcalar = []
    if settings.GEMINI_API_KEY:
        parcalar.append(f"gemini:{settings.GEMINI_MODEL}")
    if settings.GROQ_API_KEY:
        parcalar.append(f"groq:{settings.GROQ_MODEL}")
    return "+".join(parcalar) or "yok"


def json_ozet(veri: BaseModel) -> str:
    """Log/hata mesajlarında kullanılan kısa gösterim (sır taşımaz)."""
    return json.dumps(veri.model_dump(mode="json"), ensure_ascii=False)[:400]
