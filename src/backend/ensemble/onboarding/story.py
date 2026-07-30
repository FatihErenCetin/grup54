"""Epic / user story modelleri + LLM çıktısının deterministik temizliği (#340).

§8.5 adım 2: "AI taslaklar: brief -> epic'ler -> user story'ler ('Bir <rol>
olarak <istek> istiyorum, böylece <fayda>') + kabul kriteri + puan tahmini".

Bu dosyada **üretim yok, doğrulama var**. Üretimi `drafter.py` (LLM) yapar;
burası modelin döndürdüğü ham yapıyı bir sonraki adımın (sprint dağıtımı)
güvenle tüketebileceği hale getirir:

  * puanlar Fibonacci kümesine OTURTULUR (model "4" ya da "20" diyebiliyor;
    sprint bütçesi tamsayı puanlarla çalışır),
  * `epic_id` ve `bagimliliklar` içindeki HAYALİ referanslar atılır (modelin
    var olmayan bir story'e bağımlılık uydurması ölçülen bir davranış —
    atılmazsa topolojik sıralama sonsuza kadar bekler),
  * boş/eksik cümle parçası olan story ELENİR (yarım story "Bir  olarak
    istiyorum, böylece " diye render edilirdi).

Her temizlik SESSİZ DEĞİL: ne atıldıysa `TemizlikRaporu.dusenler`de döner ve
API cevabında kullanıcıya gösterilir (sessiz düşüş yasağı).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# Planning poker dağarcığı. Model bunun dışında bir sayı verirse en YAKIN
# değere oturtulur — reddetmek yerine oturtmak, tek bir kötü puan yüzünden
# tüm taslağı çöpe atmamak için (puan zaten bir TAHMİN, insan düzeltecek).
FIBONACCI_PUANLAR: tuple[int, ...] = (1, 2, 3, 5, 8, 13)


class Epic(BaseModel):
    id: str
    baslik: str
    aciklama: str = ""


class UserStory(BaseModel):
    """Kanonik user-story formu (§8.5) — cümle PARÇALARI ayrı tutulur.

    Neden tek bir `cumle: str` değil: sprint dağıtımı `puan`a, board `rol`e,
    scope kontrolü `istek`e bakar. Tek metne sıkıştırılsaydı her tüketici
    kendi ayrıştırıcısını yazardı. Cümle `olarak_cumle()` ile TEK yerde
    kurulur (drift yok).
    """

    id: str
    epic_id: str
    rol: str
    istek: str
    fayda: str
    kabul_kriterleri: list[str] = Field(default_factory=list)
    puan: int
    oncelik: int = 3
    bagimliliklar: list[str] = Field(default_factory=list)

    def olarak_cumle(self) -> str:
        return f"Bir {self.rol} olarak {self.istek} istiyorum, böylece {self.fayda}."


class DusenStory(BaseModel):
    """Elenen/düzeltilen bir öğe — sebebiyle birlikte (sessiz düşüş yasağı)."""

    id: str
    neden: str


class StoryTaslagi(BaseModel):
    epicler: list[Epic] = Field(default_factory=list)
    storyler: list[UserStory] = Field(default_factory=list)
    dusenler: list[DusenStory] = Field(default_factory=list)

    @property
    def toplam_puan(self) -> int:
        return sum(s.puan for s in self.storyler)


def fibonacci_oturt(puan: float) -> int:
    """En yakın Fibonacci puanına oturtur (eşitlikte KÜÇÜK olan kazanır).

    Eşitlikte küçüğü seçmek bilinçli: tahmin şişmesi sprint bütçesini
    doldurur ve dağıtımda story dışarıda kalır; küçük tahminin bedeli ise
    insanın onay ekranında düzeltmesidir (K6 zaten insanı oraya koyuyor).
    """
    return min(FIBONACCI_PUANLAR, key=lambda f: (abs(f - puan), f))


def temizle(taslak: StoryTaslagi) -> StoryTaslagi:
    """Ham LLM taslağını tüketilebilir hale getirir. Girdi DEĞİŞTİRİLMEZ."""
    dusenler: list[DusenStory] = list(taslak.dusenler)

    epicler: list[Epic] = []
    gorulen_epic: set[str] = set()
    for epic in taslak.epicler:
        if not epic.id.strip() or not epic.baslik.strip():
            dusenler.append(DusenStory(id=epic.id or "(id yok)", neden="epic id/başlık boş"))
            continue
        if epic.id in gorulen_epic:
            dusenler.append(DusenStory(id=epic.id, neden="epic id tekrar etti"))
            continue
        gorulen_epic.add(epic.id)
        epicler.append(epic)

    # 1. geçiş: yapısal olarak geçerli story'ler + gerçek id kümesi.
    gecerli: list[UserStory] = []
    gorulen_story: set[str] = set()
    for story in taslak.storyler:
        eksik = [
            ad
            for ad, deger in (
                ("id", story.id),
                ("rol", story.rol),
                ("istek", story.istek),
                ("fayda", story.fayda),
            )
            if not deger.strip()
        ]
        if eksik:
            dusenler.append(
                DusenStory(
                    id=story.id or "(id yok)",
                    neden=f"story cümlesinin parçaları eksik: {', '.join(eksik)}",
                )
            )
            continue
        if story.id in gorulen_story:
            dusenler.append(DusenStory(id=story.id, neden="story id tekrar etti"))
            continue
        gorulen_story.add(story.id)
        gecerli.append(story)

    # 2. geçiş: referanslar (epic + bağımlılık) ve puan normalizasyonu.
    # İki geçiş şart: bir story kendinden SONRA gelen bir story'e bağımlı
    # olabilir; tek geçişte o bağımlılık "hayali" sanılıp atılırdı.
    ilk_epic = epicler[0].id if epicler else ""
    temiz: list[UserStory] = []
    for story in gecerli:
        yeni = story.model_copy(deep=True)

        if yeni.epic_id not in gorulen_epic:
            if ilk_epic:
                dusenler.append(
                    DusenStory(
                        id=yeni.id,
                        neden=f"epic_id '{yeni.epic_id}' yok — '{ilk_epic}' epic'ine bağlandı",
                    )
                )
                yeni.epic_id = ilk_epic
            else:
                dusenler.append(
                    DusenStory(id=yeni.id, neden="hiç epic yok — story epic'siz kaldı")
                )
                yeni.epic_id = ""

        hayali = [b for b in yeni.bagimliliklar if b not in gorulen_story or b == yeni.id]
        if hayali:
            dusenler.append(
                DusenStory(
                    id=yeni.id,
                    neden=f"var olmayan/kendine dönük bağımlılık atıldı: {', '.join(hayali)}",
                )
            )
            yeni.bagimliliklar = [b for b in yeni.bagimliliklar if b not in hayali]

        oturtulmus = fibonacci_oturt(yeni.puan)
        if oturtulmus != yeni.puan:
            dusenler.append(
                DusenStory(
                    id=yeni.id,
                    neden=f"puan {yeni.puan} -> {oturtulmus} (Fibonacci dağarcığına oturtuldu)",
                )
            )
            yeni.puan = oturtulmus

        yeni.oncelik = max(1, min(5, yeni.oncelik))
        temiz.append(yeni)

    return StoryTaslagi(epicler=epicler, storyler=temiz, dusenler=dusenler)
