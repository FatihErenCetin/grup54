"""Kapasiteye göre sprint dağıtımı (#340, §8.5 adım 3) — **DETERMİNİSTİK**.

> "AI kapasiteye göre sprint dağıtımı önerir (ekip × müsaitlik × sprint sayısı
>  -> sprint başı puan bütçesi; öncelik + bağımlılığa göre yerleştir)."

**LLM'e bırakılmaz** — bu bir aritmetik + çizge sıralaması problemidir, yargı
değil. Modele sordurmanın üç somut bedeli olurdu: (1) aynı girdi iki farklı
plan üretir (kullanıcı "neden değişti" diye sorar, cevabımız yok), (2) toplam
puanın bütçeye eşit olduğunu garanti edemeyiz (model toplama yapmaz, tahmin
eder), (3) kota bitince plan da biter. Burada hiçbiri olmaz: fonksiyon saf,
girdi -> çıktı tek anlamlı, ağ yok.

Bütçe nasıl bulunur (sihirli sabit YOK)
---------------------------------------
Ekip hızını (velocity) bilmiyoruz — yeni takımın geçmiş verisi yoktur ve
"kişi başı sprint başına 8 puan" gibi bir sabit uydurmak, tam da bu repoda
kaçındığımız türden keyfi bir büyüklük olurdu. Bunun yerine bütçe TOPLAM
BACKLOG'un kapasiteye göre PAYLAŞTIRILMASIDIR:

    ağırlık_i  = ekip_büyüklüğü × müsaitlik_i
    bütçe_i    = toplam_puan × ağırlık_i / Σ ağırlık

Sonuç: bütçelerin toplamı HER ZAMAN toplam puana eşittir (en-büyük-kalan
yöntemiyle yuvarlanır) ve müsaitliği düşük sprint daha az iş alır. "Ekip ×
müsaitlik × sprint sayısı" çarpımının anlamı budur — mutlak bir hız iddiası
değil, göreli bir paylaştırma.

Yerleştirme: bağımlılık sırası (topolojik) + öncelik, sonra ilk-uyan (first
fit). Hiçbir story SESSİZCE düşmez — bütçeye sığmayan story en çok yeri olan
sprinte konur ve `uyarilar`da ADIYLA raporlanır.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from ensemble.onboarding.story import UserStory


class Kapasite(BaseModel):
    """Sprint dağıtımının TEK girdisi — brief'in `kisitlar` alanından türer."""

    ekip_buyuklugu: int = Field(ge=1, le=100)
    sprint_sayisi: int = Field(ge=1, le=20)
    # Sprint başına müsaitlik (0 < x <= 1). Verilmezse hepsi 1.0. Gerçek
    # hayatta ilk sprint kurulumla, son sprint teslimle geçer — bu liste tam
    # olarak o farkı ifade etmek için var.
    musaitlik: list[float] | None = None

    @field_validator("musaitlik")
    @classmethod
    def _musaitlik_gecerli(cls, deger: list[float] | None) -> list[float] | None:
        if deger is None:
            return None
        # 0 müsaitlik "kapasitesi olmayan sprint" demek olurdu ve toplam ağırlık
        # 0'a düşebilirdi (sıfıra bölme). Böyle bir sprint varsa doğru modelleme
        # `sprint_sayisi`'nı azaltmaktır — sessizce kabul edip payını 0 yapmak,
        # kullanıcının fark etmeyeceği bir plan bozukluğu üretirdi.
        if any(not (0 < x <= 1) for x in deger):
            raise ValueError("müsaitlik değerleri 0 ile 1 arasında olmalı (0 hariç)")
        return deger

    def agirliklar(self) -> list[float]:
        musaitlik = self.musaitlik or [1.0] * self.sprint_sayisi
        if len(musaitlik) != self.sprint_sayisi:
            raise ValueError(
                f"müsaitlik listesi {len(musaitlik)} eleman taşıyor, "
                f"sprint sayısı {self.sprint_sayisi}"
            )
        return [self.ekip_buyuklugu * m for m in musaitlik]


class SprintDilimi(BaseModel):
    sprint: int  # 1 tabanlı — kullanıcıya "Sprint 1" diye görünür
    butce: int
    yuk: int
    story_idler: list[str] = Field(default_factory=list)


class SprintPlani(BaseModel):
    dilimler: list[SprintDilimi]
    toplam_puan: int
    uyarilar: list[str] = Field(default_factory=list)


def _butceleri_dagit(toplam_puan: int, agirliklar: list[float]) -> list[int]:
    """En-büyük-kalan (largest remainder) paylaştırma.

    Basit `round()` kullanılsaydı bütçelerin toplamı toplam puandan sapardı
    (ör. 3 sprint × 10/3 -> 3+3+3=9, bir puan buharlaşır). Bu yöntemde
    Σ bütçe == toplam_puan HER ZAMAN sağlanır.
    """
    toplam_agirlik = sum(agirliklar)
    ham = [toplam_puan * a / toplam_agirlik for a in agirliklar]
    taban = [int(x) for x in ham]
    kalan = toplam_puan - sum(taban)
    # Kesirli kısmı en büyük olana +1; eşitlikte küçük indis (erken sprint)
    # kazanır — erken sprintte biraz fazla iş, geç sprintte fazladan iş
    # olmasından yeğdir (teslim tarihi son sprinttedir).
    sira = sorted(range(len(ham)), key=lambda i: (-(ham[i] - taban[i]), i))
    for i in sira[:kalan]:
        taban[i] += 1
    return taban


def _topolojik_sira(storyler: list[UserStory]) -> tuple[list[UserStory], list[str]]:
    """Bağımlılık sırası + öncelik. Döngü varsa KIRAR ve uyarı döner.

    Sıralama anahtarı `(oncelik, -puan, id)`: önce yüksek öncelik (1 = en
    yüksek), eşitlikte büyük story (erken başlasın, riski erken görülsün),
    sonra id — üçüncü anahtar sıralamayı TAM DETERMİNİSTİK yapar (aynı girdi
    -> aynı plan; testin dayanağı budur).
    """
    kalan = {s.id: s for s in storyler}
    bagimlilik = {s.id: [b for b in s.bagimliliklar if b in kalan] for s in storyler}
    sira: list[UserStory] = []
    uyarilar: list[str] = []

    def anahtar(story: UserStory) -> tuple[int, int, str]:
        return (story.oncelik, -story.puan, story.id)

    yerlesen: set[str] = set()
    while kalan:
        hazir = [s for s in kalan.values() if all(b in yerlesen for b in bagimlilik[s.id])]
        if not hazir:
            # Döngü: kalanları önceliğe göre ekle ve SÖYLE. Sessizce atmak
            # story kaybı, sonsuz döngü ise askıda kalma olurdu.
            dongu = sorted(kalan)
            uyarilar.append(
                "Bağımlılık döngüsü var — şu story'ler döngüde ve öncelik "
                f"sırasına göre yerleştirildi: {', '.join(dongu)}"
            )
            sira.extend(sorted(kalan.values(), key=anahtar))
            break
        secilen = min(hazir, key=anahtar)
        sira.append(secilen)
        yerlesen.add(secilen.id)
        del kalan[secilen.id]

    return sira, uyarilar


def sprint_dagit(storyler: list[UserStory], kapasite: Kapasite) -> SprintPlani:
    """Story'leri kapasiteye göre sprintlere yerleştirir — saf fonksiyon."""
    agirliklar = kapasite.agirliklar()
    toplam_puan = sum(s.puan for s in storyler)
    butceler = _butceleri_dagit(toplam_puan, agirliklar)

    dilimler = [
        SprintDilimi(sprint=i + 1, butce=butceler[i], yuk=0)
        for i in range(kapasite.sprint_sayisi)
    ]
    if not storyler:
        return SprintPlani(
            dilimler=dilimler,
            toplam_puan=0,
            uyarilar=["Puanlanmış story yok — dağıtılacak iş bulunamadı."],
        )

    sira, uyarilar = _topolojik_sira(storyler)
    yerlesim: dict[str, int] = {}

    for story in sira:
        # Bağımlı olduğu story'nin sprintinden ÖNCE olamaz. Aynı sprint
        # serbest: iki iş aynı iki haftada sırayla yapılabilir; katı "sonraki
        # sprint" kuralı planı gereksiz yere uzatırdı.
        en_erken = max(
            (yerlesim[b] for b in story.bagimliliklar if b in yerlesim),
            default=0,
        )
        adaylar = dilimler[en_erken:]
        hedef = next((d for d in adaylar if d.yuk + story.puan <= d.butce), None)
        if hedef is None:
            # Hiçbir sprinte sığmadı -> EN ÇOK YERİ OLANA koy ve söyle.
            # Alternatif "yerleşmeyenler" kutusu olurdu; ama plan çıktısının
            # tamamı bir TASLAK (K6) ve insan onaylayacak — story'i plandan
            # düşürmek, onu görünmez kılmak olurdu.
            hedef = max(adaylar, key=lambda d: (d.butce - d.yuk, -d.sprint))
            uyarilar.append(
                f"{story.id} ({story.puan} puan) hiçbir sprintin bütçesine sığmadı; "
                f"Sprint {hedef.sprint} bütçesi aşılarak yerleştirildi."
            )
        hedef.yuk += story.puan
        hedef.story_idler.append(story.id)
        yerlesim[story.id] = hedef.sprint - 1

        # Bootcamp PM kuralı (grup54 planı §2.4): "story başına puan sprint
        # hedefinin yarısını geçmez". Engellemiyoruz — bölme kararı insanın.
        if hedef.butce > 0 and story.puan * 2 > hedef.butce:
            uyarilar.append(
                f"{story.id} tek başına Sprint {hedef.sprint} bütçesinin yarısından "
                f"büyük ({story.puan}/{hedef.butce}) — bölünmesi önerilir."
            )

    return SprintPlani(dilimler=dilimler, toplam_puan=toplam_puan, uyarilar=uyarilar)


def kapasite_briefden(
    ekip_buyuklugu: int | None, sprint_sayisi: int | None
) -> Kapasite | None:
    """Brief kısıtlarından `Kapasite` türetir; eksikse `None` — UYDURMAZ.

    Varsayılan bir ekip büyüklüğü/sprint sayısı seçmek (ör. "3 sprint") bu
    projeye özel bir sayıyı her kullanıcının planına sızdırırdı. Eksikse plan
    ÜRETİLMEZ; `intake.eksik_alanlar()` zaten kullanıcıya bunu sorar.
    """
    if ekip_buyuklugu is None or sprint_sayisi is None:
        return None
    return Kapasite(ekip_buyuklugu=ekip_buyuklugu, sprint_sayisi=sprint_sayisi)
