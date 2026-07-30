"""Onboarding intake — SABİT hedef şema + "kaybolmama" mekaniği (#340, §8.5).

Bu modül sihirbazın **deterministik çekirdeğidir**: hiçbir LLM çağrısı yapmaz,
hiçbir ağ bağlantısı kurmaz, hiçbir dosya yazmaz. Sadece üç soruyu yanıtlar:

  1. Hedef şema neydi?            -> `Brief` (yalnız §8.5'teki altı alan)
  2. Neresi eksik/belirsiz?       -> `eksik_alanlar()`
  3. Sırada hangi soru var?       -> `ana_sorular()` / `bosluk_sorulari()`

**Neden LLM değil:** §8.5'in "kaybolmama" vaadi üç mekanizmaya dayanıyor —
sabit şema, sınırlı soru derinliği, taslak-sonra-onay. Üçü de KURAL'dır,
yargı değil. Kuralı modele sordurmak (a) kotayı yakar, (b) aynı girdide farklı
davranır, (c) sağlayıcı düşünce sihirbazı tamamen durdururdu. Ölçülen kota
gerçeği 20 istek/GÜN (bkz. `integrations/gemini/client.py::_bekleme`) — bu
modül sayesinde "soru-cevap" ve "kendim girerim" modları **sıfır LLM
çağrısıyla** uçtan uca çalışır.

LLM yalnız iki yerde: serbest metinden yapı çıkarma (`brief_drafter.py`) ve
epic/story taslağı (`story_draft.py`). İkisi de düşerse `degraded` BEYAN
edilir, sahte taslak üretilmez (#252 sözleşmesinin onboarding'deki karşılığı).

Uydurma yasağı — iki AYRI durum, tek modelde karıştırılmaz:
  * `eksik_alanlar()`  -> alan BOŞ; kimse doldurmadı. UI bunu "eksik" gösterir.
  * `Brief.varsayimlar` -> alanı AI doldurdu (kullanıcı "bununla devam et"
    dedi). Değer VAR ama kullanıcının değil — bu yüzden ayrıca işaretlenir.
İkisi tek bayrağa sıkıştırılsaydı "kullanıcı söyledi" ile "AI varsaydı"
ayırt edilemezdi; kabul kriteri tam da bu ayrımı istiyor.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# §8.5'in sabit hedef şeması — intake YALNIZCA bunları doldurur. Liste
# BİLEREK kapalıdır: yeni alan eklemek şemayı genişletmek demektir ve
# "kaybolmama" garantisini zayıflatır (her yeni alan bir soru turu daha).
ALAN_IDLERI: tuple[str, ...] = (
    "urun_tek_cumle",
    "hedef_kullanicilar",
    "cekirdek_ozellikler",
    "kapsam_disi",
    "kisitlar",
    "basari_hedefi",
)

# MVP kapsamı 3-7 madde (§8.5). Altı sınır bir KABUL kriteridir: 3'ten azsa
# story üretmeye yetmez (boşluk sorusu tetiklenir), 7'den fazlaysa "MVP"
# olmaktan çıkar (uyarı — ama engellenmez, kullanıcının kararı).
CEKIRDEK_OZELLIK_MIN = 3
CEKIRDEK_OZELLIK_MAX = 7

# Bir metin alanının "cevaplanmış" sayılması için gereken en az karakter.
# "yok", "?" gibi tek kelimelik cevaplar story üretmeye yetmez -> boşluk
# sorusu tetiklenir (§8.5: "yalnız cevap story üretmeye yetmeyecek kadar
# muğlaksa derinleş").
_ANLAMLI_METIN_UZUNLUGU = 12

# "En çok iki tur" (§8.5) — sorgu yağmuru yasağının SAYISAL karşılığı.
MAKS_BOSLUK_TURU = 2

Mod = Literal["anlat", "soru_cevap", "kendim"]


class Kisitlar(BaseModel):
    """§8.5 "Kısıtlar" alanı — tek bir alan ama içi yapılı.

    Sprint dağıtımı (`sprint_plan.py`) `ekip_buyuklugu` + `sprint_sayisi`
    olmadan bütçe hesaplayamaz; bu yüzden bu ikisi alanın "dolu" sayılması
    için ZORUNLU (bkz. `_kisit_durumu`). Diğerleri bağlam bilgisidir.
    """

    ekip_buyuklugu: int | None = None
    yetkinlikler: list[str] = Field(default_factory=list)
    sprint_sayisi: int | None = None
    sprint_gun: int | None = None
    teknolojiler: list[str] = Field(default_factory=list)
    entegrasyonlar: list[str] = Field(default_factory=list)


class Varsayim(BaseModel):
    """AI'nın kullanıcı adına doldurduğu bir alan — DEĞER değil, İŞARET.

    "Bununla devam et" dendiğinde üretilir. UI bunu ayrı bir renkte/rozette
    gösterir ki kullanıcı neyi onayladığını bilsin (K6: insan onaylar).
    """

    alan: str
    deger_ozeti: str
    gerekce: str


class Brief(BaseModel):
    """SABİT hedef şema (§8.5) — sihirbazın topladığı bilginin TAMAMI.

    Tüm alanlar varsayılanlı: yarım bir brief geçerli bir nesnedir. Eksiklik
    bir doğrulama HATASI değil, raporlanan bir DURUMDUR (`eksik_alanlar`) —
    aksi halde kullanıcı ilk adımda 422 duvarına toslardı ve "her an bununla
    devam et diyebilir" vaadi imkânsız olurdu.
    """

    urun_tek_cumle: str = ""
    hedef_kullanicilar: list[str] = Field(default_factory=list)
    cekirdek_ozellikler: list[str] = Field(default_factory=list)
    kapsam_disi: list[str] = Field(default_factory=list)
    kisitlar: Kisitlar = Field(default_factory=Kisitlar)
    basari_hedefi: str = ""
    varsayimlar: list[Varsayim] = Field(default_factory=list)


class Eksik(BaseModel):
    """Bir alanın neden "hazır değil" sayıldığı — sebep TAŞINIR, gizlenmez."""

    alan: str
    neden: Literal["bos", "yetersiz"]
    aciklama: str


class Uyari(BaseModel):
    """Engelleyici olmayan gözlem (ör. 7'den fazla çekirdek özellik)."""

    alan: str
    aciklama: str


class Soru(BaseModel):
    """Tek bir hedefli soru. `coklu=True` -> cevap satır satır listeye ayrılır."""

    alan: str
    metin: str
    ipucu: str
    coklu: bool = False


# Her alan için TEK ana soru (§8.5: "her alan için 1 ana soru"). Metinler
# bilerek kısa ve somut — "ürününüzü anlatın" gibi açık uçlu sorular tam da
# kullanıcının kaybolduğu yerdir.
_ANA_SORULAR: tuple[Soru, ...] = (
    Soru(
        alan="urun_tek_cumle",
        metin="Ürünü tek cümlede anlat: ne, kime, hangi problemi çözüyor?",
        ipucu="Örn: 'Yazılım ekipleri için, aynı dosyaya iki kişinin aynı anda dokunduğunu erkenden gösteren bir çakışma radarı.'",
    ),
    Soru(
        alan="hedef_kullanicilar",
        metin="Hedef kullanıcılar kim? (her satıra bir rol)",
        ipucu="Örn: 'takım lideri', 'geliştirici', 'ürün sahibi'",
        coklu=True,
    ),
    Soru(
        alan="cekirdek_ozellikler",
        metin=f"MVP kapsamındaki çekirdek özellikler neler? ({CEKIRDEK_OZELLIK_MIN}-{CEKIRDEK_OZELLIK_MAX} madde, her satıra bir madde)",
        ipucu="Demoyu ayakta tutan asgari liste. Sonra eklenecekler buraya değil, kapsam dışına.",
        coklu=True,
    ),
    Soru(
        alan="kapsam_disi",
        metin="Bilinçli olarak NE YAPMAYACAKSINIZ? (her satıra bir madde)",
        ipucu="Sınırı bu çizer; scope-drift kararları buna bakar. Örn: 'mobil uygulama', 'çok dillilik'.",
        coklu=True,
    ),
    Soru(
        alan="kisitlar",
        metin="Kısıtlar: kaç kişilik ekip, kaç sprint, hangi teknolojiler/entegrasyonlar?",
        ipucu="Örn: '4 kişi, 3 sprint (2 hafta), Python + React, GitHub API'. Ekip sayısı ve sprint sayısı sprint dağıtımı için gerekli.",
    ),
    Soru(
        alan="basari_hedefi",
        metin="Başarı/demo hedefi nedir? Neyi gösterebilirsen 'oldu' dersin?",
        ipucu="Örn: 'Canlı demoda iki geliştiricinin çakışması 30 saniye içinde radarda görünsün.'",
    ),
)

_ALAN_ADLARI: dict[str, str] = {
    "urun_tek_cumle": "Ürün tek cümle",
    "hedef_kullanicilar": "Hedef kullanıcılar",
    "cekirdek_ozellikler": "Çekirdek özellikler",
    "kapsam_disi": "Kapsam dışı",
    "kisitlar": "Kısıtlar",
    "basari_hedefi": "Başarı / demo hedefi",
}


def alan_adi(alan: str) -> str:
    return _ALAN_ADLARI.get(alan, alan)


def ana_sorular() -> list[Soru]:
    """Soru-cevap modunun ilk turu: alan başına TEK soru, altı soru toplam."""
    return list(_ANA_SORULAR)


def _metin_yetersiz(deger: str) -> bool:
    return len(deger.strip()) < _ANLAMLI_METIN_UZUNLUGU


def _kisit_durumu(kisitlar: Kisitlar) -> Eksik | None:
    """Kısıtlar alanı sprint dağıtımına yetiyor mu?

    `ekip_buyuklugu` VE `sprint_sayisi` -> deterministik bütçe hesabının iki
    zorunlu girdisi (bkz. `sprint_plan.sprint_dagit`). Biri yoksa alan
    "yetersiz"dir; ikisi de yoksa "boş".
    """
    dolu = [
        kisitlar.ekip_buyuklugu is not None,
        kisitlar.sprint_sayisi is not None,
    ]
    if not any(dolu) and not (kisitlar.teknolojiler or kisitlar.entegrasyonlar):
        return Eksik(
            alan="kisitlar",
            neden="bos",
            aciklama="Ekip büyüklüğü ve sprint sayısı yok — sprint dağıtımı hesaplanamaz.",
        )
    if not all(dolu):
        yok = "ekip büyüklüğü" if kisitlar.ekip_buyuklugu is None else "sprint sayısı"
        return Eksik(
            alan="kisitlar",
            neden="yetersiz",
            aciklama=f"{yok.capitalize()} verilmemiş — sprint dağıtımı bu olmadan hesaplanamaz.",
        )
    return None


def eksik_alanlar(brief: Brief) -> list[Eksik]:
    """Şemanın hangi alanları story üretmeye YETMİYOR — deterministik.

    "Eksik" burada `None`/`""` demek DEĞİL; "bu haliyle bir sonraki adımı
    besleyemez" demek. Bu yüzden `cekirdek_ozellikler=["ui"]` (tek madde) da
    eksiktir: üç epic'lik bir taslak çıkmaz.
    """
    eksikler: list[Eksik] = []

    if not brief.urun_tek_cumle.strip():
        eksikler.append(
            Eksik(alan="urun_tek_cumle", neden="bos", aciklama="Ürün tek cümlesi boş.")
        )
    elif _metin_yetersiz(brief.urun_tek_cumle):
        eksikler.append(
            Eksik(
                alan="urun_tek_cumle",
                neden="yetersiz",
                aciklama="Tek cümle çok kısa — ne/kime/hangi problem üçlüsü okunmuyor.",
            )
        )

    if not brief.hedef_kullanicilar:
        eksikler.append(
            Eksik(
                alan="hedef_kullanicilar",
                neden="bos",
                aciklama="Hedef kullanıcı yok — user story'nin '<rol>' kısmı yazılamaz.",
            )
        )

    ozellik_sayisi = len(brief.cekirdek_ozellikler)
    if ozellik_sayisi == 0:
        eksikler.append(
            Eksik(
                alan="cekirdek_ozellikler",
                neden="bos",
                aciklama="Çekirdek özellik yok — epic/story taslağının girdisi bu listedir.",
            )
        )
    elif ozellik_sayisi < CEKIRDEK_OZELLIK_MIN:
        eksikler.append(
            Eksik(
                alan="cekirdek_ozellikler",
                neden="yetersiz",
                aciklama=(
                    f"{ozellik_sayisi} madde var, en az {CEKIRDEK_OZELLIK_MIN} bekleniyor "
                    "— bu kadarı bir MVP kapsamı çizmiyor."
                ),
            )
        )

    if not brief.kapsam_disi:
        eksikler.append(
            Eksik(
                alan="kapsam_disi",
                neden="bos",
                aciklama="Kapsam dışı boş — sınır çizilmemiş, scope-drift kararı dayanaksız kalır.",
            )
        )

    kisit_eksigi = _kisit_durumu(brief.kisitlar)
    if kisit_eksigi is not None:
        eksikler.append(kisit_eksigi)

    if not brief.basari_hedefi.strip():
        eksikler.append(
            Eksik(alan="basari_hedefi", neden="bos", aciklama="Başarı/demo hedefi boş.")
        )
    elif _metin_yetersiz(brief.basari_hedefi):
        eksikler.append(
            Eksik(
                alan="basari_hedefi",
                neden="yetersiz",
                aciklama="Hedef çok kısa — 'neyi gösterirsen oldu' okunmuyor.",
            )
        )

    return eksikler


def uyarilar(brief: Brief) -> list[Uyari]:
    """Engellemeyen ama söylenmesi gereken gözlemler (sessiz düşüş yasağı)."""
    cikti: list[Uyari] = []
    if len(brief.cekirdek_ozellikler) > CEKIRDEK_OZELLIK_MAX:
        cikti.append(
            Uyari(
                alan="cekirdek_ozellikler",
                aciklama=(
                    f"{len(brief.cekirdek_ozellikler)} çekirdek özellik var; MVP için "
                    f"önerilen üst sınır {CEKIRDEK_OZELLIK_MAX}. Fazlasını kapsam dışına "
                    "taşımayı düşün."
                ),
            )
        )
    return cikti


def bosluk_sorulari(brief: Brief, tur: int) -> list[Soru]:
    """YALNIZ boşluk/belirsizlik için hedefli soru — sorgu yağmuru DEĞİL.

    İki kural birlikte "kaybolmama"yı garanti eder:
      * Yalnız `eksik_alanlar()` dönen alanlar sorulur (dolu alan tekrar
        sorulmaz — kullanıcının verdiği cevabı ikinci kez istemek, sihirbazın
        kullanıcıyı dinlemediği hissini veren tam olarak o davranıştır).
      * `tur > MAKS_BOSLUK_TURU` -> BOŞ liste. Üçüncü tur YOKTUR; bu noktadan
        sonra tek yol "bununla devam et" (AI varsayımlarla doldurur ve
        işaretler) ya da elle düzenlemedir.
    """
    if tur > MAKS_BOSLUK_TURU:
        return []
    hedefler = {e.alan for e in eksik_alanlar(brief)}
    return [soru for soru in _ANA_SORULAR if soru.alan in hedefler]


def cevaplari_briefe_cevir(cevaplar: dict[str, str], mevcut: Brief | None = None) -> Brief:
    """Soru-cevap cevaplarını şemaya oturtur — **LLM YOK, mekanik dönüşüm**.

    Her cevap zaten kendi alanına adreslidir (soru alan id'siyle soruldu), o
    yüzden burada "anlama" gerekmez: çok satırlı alanlar satırlara bölünür,
    kısıtlar alanı sayı yakalamaya çalışır. Bu, `wizard.py`'nin "gh -> md
    mekanik aynası" ile aynı dürüstlük çizgisi: AI değil, dönüşüm.

    `mevcut` verilirse ÜZERİNE yazılır (ikinci tur boşluk cevapları): yalnız
    gelen alanlar güncellenir, dokunulmayanlar korunur.
    """
    brief = (mevcut or Brief()).model_copy(deep=True)

    if "urun_tek_cumle" in cevaplar:
        brief.urun_tek_cumle = cevaplar["urun_tek_cumle"].strip()
    if "basari_hedefi" in cevaplar:
        brief.basari_hedefi = cevaplar["basari_hedefi"].strip()
    if "hedef_kullanicilar" in cevaplar:
        brief.hedef_kullanicilar = _satirlar(cevaplar["hedef_kullanicilar"])
    if "cekirdek_ozellikler" in cevaplar:
        brief.cekirdek_ozellikler = _satirlar(cevaplar["cekirdek_ozellikler"])
    if "kapsam_disi" in cevaplar:
        brief.kapsam_disi = _satirlar(cevaplar["kapsam_disi"])
    if "kisitlar" in cevaplar:
        brief.kisitlar = _kisit_ayikla(cevaplar["kisitlar"], brief.kisitlar)

    # Kullanıcı bir alanı ELLE doldurduysa o alanın AI varsayımı artık
    # geçersizdir — işareti bırakmak, kullanıcının kendi cümlesini "AI
    # varsaydı" diye göstermek olurdu.
    dokunulan = set(cevaplar)
    brief.varsayimlar = [v for v in brief.varsayimlar if v.alan not in dokunulan]
    return brief


def _satirlar(ham: str) -> list[str]:
    """Çok satırlı cevabı listeye böler; madde işaretlerini ve boşları atar."""
    cikti: list[str] = []
    for satir in ham.replace(";", "\n").splitlines():
        temiz = satir.strip().lstrip("-•*").strip()
        if temiz:
            cikti.append(temiz)
    return cikti


_SAYI_ETIKETLERI: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ekip_buyuklugu", ("kişi", "kisi", "geliştirici", "gelistirici", "developer")),
    ("sprint_sayisi", ("sprint",)),
    ("sprint_gun", ("gün", "gun", "hafta")),
)


def _kisit_ayikla(ham: str, mevcut: Kisitlar) -> Kisitlar:
    """Serbest kısıt cümlesinden sayıları yakalar — tahmin YOK, yalnız eşleşme.

    "4 kişi, 3 sprint" gibi yazımlarda sayıyı ETİKETİYLE birlikte arar; etiket
    yoksa hiçbir şey yazılmaz (yanlış alana sayı koymaktansa boş bırakmak
    yeğdir — boşluk zaten `eksik_alanlar()` ile görünür olur). Metnin tamamı
    `teknolojiler`e ham olarak DÜŞMEZ; teknoloji çıkarımı bir yargıdır, bu
    modülün işi değil (LLM modunda `brief_drafter` yapar).
    """
    import re

    kisitlar = mevcut.model_copy(deep=True)
    dusuk = ham.lower()
    for alan, etiketler in _SAYI_ETIKETLERI:
        for etiket in etiketler:
            eslesme = re.search(rf"(\d+)\s*(?:-|\s)?\s*{re.escape(etiket)}", dusuk)
            if eslesme:
                deger = int(eslesme.group(1))
                if alan == "sprint_gun" and etiket in ("hafta",):
                    deger *= 7
                setattr(kisitlar, alan, deger)
                break
    return kisitlar
