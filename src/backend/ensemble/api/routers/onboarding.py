"""Onboarding sihirbazı HTTP yüzü (#340, §8.5).

Altı uç, tek akış:

    GET  /onboarding/durum    -> bu kurulumda sihirbaz ne yapabilir (ÖNCEDEN)
    POST /onboarding/sorular  -> sıradaki hedefli sorular   (deterministik)
    POST /onboarding/brief    -> sabit şemayı doldur        (yalnız "anlat" modunda LLM)
    POST /onboarding/taslak   -> epic + user story taslağı  (LLM)
    POST /onboarding/plan     -> kapasiteye göre dağıtım    (deterministik)
    POST /onboarding/uygula   -> .harness/'e YAZ            (K6: insan onayı ŞART)

**Durum sunucuda tutulmaz.** Her uç taslağın tamamını alır ve tamamını döner;
istemci "şu anki taslak" sahibidir. Neden: (1) sihirbaz tek seferlik bir akış,
bir oturum tablosu + temizleyicisi eklemek kalıcı bir bakım yüküdür; (2) K6
"her çıktı düzenlenebilir taslaktır" diyor — kullanıcı ekranda düzenlediği
şeyi bir sonraki adıma gönderir, sunucudaki bir kopya ile UI arasında
ayrışma riski hiç doğmaz; (3) taslak diske ancak `uygula` ile iner, o da
onay taşır.

**Sessiz düşüş yasağı:** LLM aşamaları (`brief` "anlat" modunda, `taslak`)
sağlayıcı düşerse BOŞ SONUÇ + `degraded` döner — 200'ün içinde beyan edilmiş
bir eksiklik, `RadarResponse.degraded` deseninin aynısı. Uydurma taslak
üretilmez; istemci `degraded` doluysa uyarı çizer (bkz. OnboardingPage).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Literal

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ensemble.api.deps import SettingsDep
from ensemble.config import Settings
from ensemble.onboarding.apply import (
    MevcutDosyaHatasi,
    OnayKaydi,
    OnaysizYazmaHatasi,
    YazmaSonucu,
    harness_yaz,
)
from ensemble.onboarding.drafter import (
    OnboardingDrafterPort,
    TaslakUretilemedi,
    build_drafter,
    saglayici_adi,
)
from ensemble.onboarding.intake import (
    MAKS_BOSLUK_TURU,
    Brief,
    Eksik,
    Mod,
    Soru,
    Uyari,
    ana_sorular,
    bosluk_sorulari,
    cevaplari_briefe_cevir,
    eksik_alanlar,
    uyarilar,
)
from ensemble.onboarding.sprint_plan import Kapasite, SprintPlani, sprint_dagit
from ensemble.onboarding.story import StoryTaslagi, UserStory, temizle

logger = logging.getLogger("ensemble.onboarding")

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


# NEDEN `Path.cwd()`, NEDEN `Path(__file__).parents[N]` DEĞİL:
# `.harness/` bu üründe HER YERDE çalışma dizininden okunur —
# `FileHarnessPort()`'un varsayılan kökü `"."` ve app.py, mcp/server.py,
# engine/graph.py, store/rebuild.py hepsi onu böyle çağırıyor. macOS masaüstü
# paketi (T-305) bunu BİLEREK kullanıyor: `packaging/launcher.py::main` açılışta
# `os.chdir(data_dir)` ile cwd'yi `~/Library/Application Support/Ensemble`'a
# çeviriyor. Dosya konumundan türetilmiş bir kök orada .app paketinin İÇİNİ
# gösterirdi — salt-okunur, üstelik ürünün OKUDUĞU `.harness/`'ten BAŞKA bir
# yer: sihirbaz, kullanıcının board'da gördüğünden farklı bir dizine yazardı.
def _varsayilan_kok() -> Path:
    return Path.cwd()


# Serbest metin üst sınırları: prompt uzunluğu = maliyet. Sınırsız bir alan,
# tek bir istekle günlük kotayı yakabilirdi (ölçülen kota 20 istek/GÜN).
_MAKS_SERBEST_METIN = 8000
_MAKS_CEVAP = 2000


class OnboardingDegraded(BaseModel):
    """Bu turda ÜRETİLEMEYEN taslak — `RadarResponse.degraded` deseni (#252).

    Varlığı "sonuç eksik" demektir. İstemci bunu taslak gibi göstermemeli,
    "üretilemedi + neden" uyarısı olarak göstermelidir. `neden` sağlayıcı
    hatasının ÖZETİDİR (anahtar/sır taşımaz — hata metinleri sağlayıcı
    istemcilerinde zaten sırdan arındırılmış geliyor).
    """

    asama: Literal["brief", "story"]
    saglayici: str
    neden: str


class OnboardingDurum(BaseModel):
    """Sihirbaz bu kurulumda ne yapabilir — kullanıcı TIKLAMADAN ÖNCE bilsin.

    "İş yapmayan buton basmıyoruz" (D-34) ilkesinin onboarding karşılığı:
    hosted demoda `uygula` adımı yoktur (yazma yalnız local), sağlayıcı yoksa
    "anlat" modu taslak üretemez. İkisi de sayfada ÖNCEDEN söylenir.
    """

    mode: Literal["local", "hosted"]
    yazma_mumkun: bool
    yazma_kok: str
    # Yazma neden mümkün DEĞİL — mutlu yolda `null`. "Buton kapalı" demek
    # yetmez; kullanıcı NEDEN kapalı olduğunu bilmeli (sessiz düşüş yasağı).
    yazma_engeli: str | None = None
    harness_var: bool
    saglayici: str
    ai_kullanilabilir: bool
    maks_bosluk_turu: int = MAKS_BOSLUK_TURU


class SorularIstegi(BaseModel):
    mod: Mod
    # 1 = ana sorular (alan başına bir tane). 2+ = yalnız boşluk soruları.
    tur: int = Field(default=1, ge=1, le=10)
    brief: Brief = Field(default_factory=Brief)


class SorularYaniti(BaseModel):
    sorular: list[Soru]
    tur: int
    # true -> soru turu HAKKI BİTTİ (§8.5 "en çok iki tur"). İstemci bundan
    # sonra yalnız "bununla devam et" ya da elle düzenleme sunar.
    tur_bitti: bool
    eksikler: list[Eksik]


class BriefIstegi(BaseModel):
    mod: Mod
    serbest_metin: str = Field(default="", max_length=_MAKS_SERBEST_METIN)
    cevaplar: dict[str, str] = Field(default_factory=dict)
    brief: Brief = Field(default_factory=Brief)
    # "Bununla devam et": AI boşlukları makul varsayımlarla doldurur ve
    # varsayımları İŞARETLER (§8.5 kaybolmama kuralı).
    varsayimlarla_doldur: bool = False


class BriefYaniti(BaseModel):
    brief: Brief
    eksikler: list[Eksik]
    uyarilar: list[Uyari]
    ai_kullanildi: bool
    degraded: OnboardingDegraded | None = None


class TaslakIstegi(BaseModel):
    brief: Brief


class TaslakYaniti(BaseModel):
    taslak: StoryTaslagi
    degraded: OnboardingDegraded | None = None


class PlanIstegi(BaseModel):
    storyler: list[UserStory]
    kapasite: Kapasite


class UygulaIstegi(BaseModel):
    onay: OnayKaydi
    brief: Brief
    taslak: StoryTaslagi
    plan: SprintPlani | None = None


def get_onboarding_root(request: Request) -> Path:
    """Sihirbazın yazacağı repo kökü.

    Dependency olmasının tek sebebi TEST edilebilirlik: gerçek `.harness/`'e
    yazan bir ucu birim testinde çalıştırmak için kökün geçici bir dizine
    yönlendirilebilmesi gerekiyor (`app.dependency_overrides`). Üretimde
    değeri her zaman repo köküdür; `app.state.onboarding_root` yalnız testte
    set edilir.
    """
    return Path(getattr(request.app.state, "onboarding_root", None) or _varsayilan_kok())


OnboardingRootDep = Annotated[Path, Depends(get_onboarding_root)]


def _require_local_mode(settings: Settings) -> None:
    """Yazma yalnız local modda. Hosted'da 404 — `settings.py` KURAL 1'in
    aynısı ve aynı gerekçe: paylaşılan bir demoda herkesin sunucunun
    `.harness/`'ine yazabilmesi kabul edilemez."""
    if settings.ENSEMBLE_MODE != "local":
        raise HTTPException(
            status_code=404,
            detail="Sihirbaz yazma adımı yalnız local kurulumda vardır.",
        )


def _yazma_engeli(settings: Settings, kok: Path) -> str | None:
    """Yazmayı GERÇEKTEN engelleyen ne varsa — TIKLAMADAN ÖNCE söylenir.

    İki ayrı engel, iki ayrı cümle: (1) hosted mod (tasarım gereği), (2) kök
    dizin yazılamıyor. İkincisi "kodda var ≠ çalışıyor" sınıfının tam
    örneğidir: salt-okunur bir kökte düğme çalışır görünür, tıklanınca
    `PermissionError` -> 500 verirdi. `os.access` ile ÖNCEDEN ölçüp dürüstçe
    kapatıyoruz (fail-closed).
    """
    if settings.ENSEMBLE_MODE != "local":
        return (
            "Bu kurulum hosted modda — sihirbaz taslak üretir ama diske YAZMAZ "
            "(paylaşılan bir sunucuda herkesin .harness/'e yazması kabul edilemez). "
            "Yazmak için Ensemble'ı kendi makinende çalıştır."
        )
    if not os.access(kok, os.W_OK):
        return f"Çalışma dizinine yazılamıyor: {kok} (izinleri kontrol et)."
    return None


@router.get("/durum")
def durum(settings: SettingsDep, kok: OnboardingRootDep) -> OnboardingDurum:
    engel = _yazma_engeli(settings, kok)
    return OnboardingDurum(
        mode=settings.ENSEMBLE_MODE,
        yazma_mumkun=engel is None,
        yazma_kok=str(kok),
        yazma_engeli=engel,
        harness_var=(kok / ".harness").is_dir(),
        saglayici=saglayici_adi(settings),
        ai_kullanilabilir=build_drafter(settings) is not None,
    )


@router.post("/sorular")
def sorular(istek: SorularIstegi) -> SorularYaniti:
    """Sıradaki hedefli sorular — **LLM YOK** (bkz. `intake.py` başlığı)."""
    eksikler = eksik_alanlar(istek.brief)
    if istek.tur <= 1 and istek.mod == "soru_cevap":
        return SorularYaniti(
            sorular=ana_sorular(), tur=1, tur_bitti=False, eksikler=eksikler
        )
    liste = bosluk_sorulari(istek.brief, istek.tur)
    return SorularYaniti(
        sorular=liste,
        tur=istek.tur,
        tur_bitti=istek.tur > MAKS_BOSLUK_TURU,
        eksikler=eksikler,
    )


def _drafter_ya_da_degraded(
    settings: Settings, asama: Literal["brief", "story"]
) -> tuple[OnboardingDrafterPort | None, OnboardingDegraded | None]:
    drafter = build_drafter(settings)
    if drafter is not None:
        return drafter, None
    return None, OnboardingDegraded(
        asama=asama,
        saglayici="yok",
        neden=(
            "Hiçbir LLM sağlayıcısı yapılandırılmamış (GEMINI_API_KEY / GROQ_API_KEY / "
            "LLM_PROVIDER=ollama). Taslak üretilemez — 'Kendim girerim' ve 'Soru-cevap' "
            "modları sağlayıcı olmadan da çalışır."
        ),
    )


@router.post("/brief")
def brief_uret(istek: BriefIstegi, settings: SettingsDep) -> BriefYaniti:
    """Sabit şemayı doldurur. LLM YALNIZCA gerekiyorsa çağrılır.

    * `kendim`      -> hiç LLM yok; gelen brief doğrulanır.
    * `soru_cevap`  -> cevaplar mekanik olarak şemaya oturur (LLM yok).
    * `anlat`       -> serbest metinden yapı çıkarmak için 1 çağrı.
    * `varsayimlarla_doldur=true` + boşluk varsa -> 1 çağrı (aynı çağrıya
      birleşir: "anlat" modunda tek istek hem çıkarır hem doldurur).
    """
    brief = istek.brief
    if istek.mod == "soru_cevap" and istek.cevaplar:
        kirpilmis = {k: v[:_MAKS_CEVAP] for k, v in istek.cevaplar.items()}
        brief = cevaplari_briefe_cevir(kirpilmis, brief)

    ai_gerekli = istek.mod == "anlat" or (
        istek.varsayimlarla_doldur and bool(eksik_alanlar(brief))
    )
    if not ai_gerekli:
        return BriefYaniti(
            brief=brief,
            eksikler=eksik_alanlar(brief),
            uyarilar=uyarilar(brief),
            ai_kullanildi=False,
        )

    drafter, degraded = _drafter_ya_da_degraded(settings, "brief")
    if drafter is None:
        # Fail-open YASAK: sağlayıcı yokken "brief hazır" gibi 200 dönmüyoruz —
        # elde ne varsa o dönüyor ve eksiklik `degraded` ile BEYAN ediliyor.
        return BriefYaniti(
            brief=brief,
            eksikler=eksik_alanlar(brief),
            uyarilar=uyarilar(brief),
            ai_kullanildi=False,
            degraded=degraded,
        )

    try:
        uretilen = drafter.brief_uret(
            serbest_metin=istek.serbest_metin,
            mevcut=brief,
            varsayimlarla_doldur=istek.varsayimlarla_doldur,
        )
    except TaslakUretilemedi as exc:
        logger.info("brief taslağı üretilemedi: %s", exc)
        return BriefYaniti(
            brief=brief,
            eksikler=eksik_alanlar(brief),
            uyarilar=uyarilar(brief),
            ai_kullanildi=False,
            degraded=OnboardingDegraded(
                asama="brief", saglayici=saglayici_adi(settings), neden=str(exc)
            ),
        )

    birlesik = _brief_birlestir(brief, uretilen)
    return BriefYaniti(
        brief=birlesik,
        eksikler=eksik_alanlar(birlesik),
        uyarilar=uyarilar(birlesik),
        ai_kullanildi=True,
    )


def _brief_birlestir(mevcut: Brief, uretilen: Brief) -> Brief:
    """Kullanıcının KENDİ yazdığı alan korunur; AI yalnız BOŞLUĞU doldurur.

    Kabul kriteri "eksik alan uydurulmaz" kadar önemli olan ikinci yarısı:
    kullanıcının yazdığı da EZİLMEZ. Model, dolu bir alanı "daha iyi" bir
    cümleyle değiştirmeye eğilimlidir; bu, kullanıcının onayladığını sandığı
    metnin sessizce değişmesi demektir.
    """
    sonuc = mevcut.model_copy(deep=True)
    if not sonuc.urun_tek_cumle.strip():
        sonuc.urun_tek_cumle = uretilen.urun_tek_cumle
    if not sonuc.hedef_kullanicilar:
        sonuc.hedef_kullanicilar = uretilen.hedef_kullanicilar
    if not sonuc.cekirdek_ozellikler:
        sonuc.cekirdek_ozellikler = uretilen.cekirdek_ozellikler
    if not sonuc.kapsam_disi:
        sonuc.kapsam_disi = uretilen.kapsam_disi
    if not sonuc.basari_hedefi.strip():
        sonuc.basari_hedefi = uretilen.basari_hedefi

    kisit = sonuc.kisitlar
    yeni = uretilen.kisitlar
    if kisit.ekip_buyuklugu is None:
        kisit.ekip_buyuklugu = yeni.ekip_buyuklugu
    if kisit.sprint_sayisi is None:
        kisit.sprint_sayisi = yeni.sprint_sayisi
    if kisit.sprint_gun is None:
        kisit.sprint_gun = yeni.sprint_gun
    if not kisit.yetkinlikler:
        kisit.yetkinlikler = yeni.yetkinlikler
    if not kisit.teknolojiler:
        kisit.teknolojiler = yeni.teknolojiler
    if not kisit.entegrasyonlar:
        kisit.entegrasyonlar = yeni.entegrasyonlar

    # Varsayımlar birikir ama tekrarlamaz (alan başına en yenisi).
    alanlar = {v.alan for v in uretilen.varsayimlar}
    sonuc.varsayimlar = [
        v for v in sonuc.varsayimlar if v.alan not in alanlar
    ] + uretilen.varsayimlar
    return sonuc


@router.post("/taslak")
def taslak_uret(istek: TaslakIstegi, settings: SettingsDep) -> TaslakYaniti:
    """Brief -> epic -> user story + kabul kriteri + puan (§8.5 adım 2)."""
    drafter, degraded = _drafter_ya_da_degraded(settings, "story")
    if drafter is None:
        return TaslakYaniti(taslak=StoryTaslagi(), degraded=degraded)
    try:
        ham = drafter.story_uret(istek.brief)
    except TaslakUretilemedi as exc:
        logger.info("story taslağı üretilemedi: %s", exc)
        return TaslakYaniti(
            taslak=StoryTaslagi(),
            degraded=OnboardingDegraded(
                asama="story", saglayici=saglayici_adi(settings), neden=str(exc)
            ),
        )
    return TaslakYaniti(taslak=temizle(ham))


@router.post(
    "/plan",
    responses={400: {"description": "Kapasite tutarsız (müsaitlik listesi uzunluğu)"}},
)
def plan_uret(istek: PlanIstegi) -> SprintPlani:
    """Kapasiteye göre sprint dağıtımı — **deterministik, LLM YOK**."""
    try:
        return sprint_dagit(istek.storyler, istek.kapasite)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/uygula",
    responses={
        403: {"description": "İnsan onayı yok (K6)"},
        404: {"description": "Yazma yalnız local modda vardır"},
        409: {"description": "Hedef dosyalar zaten var — üzerine yazılmadı"},
    },
)
def uygula(
    istek: UygulaIstegi, settings: SettingsDep, kok: OnboardingRootDep
) -> YazmaSonucu:
    """Onaylanmış taslağı `.harness/`'e yazar. **K6 kapısı `apply.py`'de.**"""
    _require_local_mode(settings)
    # `/durum`un ÖNCEDEN söylediği engeli burada da uygula — istemci ekranı
    # atlanabilir (curl), ve salt-okunur kökte `PermissionError` -> 500
    # kullanıcıya hiçbir şey anlatmaz.
    if not os.access(kok, os.W_OK):
        raise HTTPException(
            status_code=409,
            detail=f"Çalışma dizinine yazılamıyor: {kok} (izinleri kontrol et).",
        )
    try:
        return harness_yaz(
            kok,
            brief=istek.brief,
            taslak=istek.taslak,
            plan=istek.plan,
            onay=istek.onay,
        )
    except OnaysizYazmaHatasi as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except MevcutDosyaHatasi as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
