from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class NormalizedEvent(BaseModel):
    """Ingest çıktısı (S2 §1, GATE 2 #14 ile dondu) — `actor_verified` (#296,
    T-296) TEK katkı: additive + varsayılanlı, donuk modele dokunmaz (bkz.
    docs/sprint3-kontratlar.md Ek G).

    Varsayılan `True` ("doğrulanmış") BİLİNÇLİ seçim: bu alanı hiç set
    etmeyen eski/başka üretim yolları (fixtures, `fake.py`, henüz
    güncellenmemiş bir adapter) sessizce "şüpheli" görünmesin — yalnızca
    GERÇEKTEN eşleşmediği bilinen yollar (bkz. integrations/github/normalize.py)
    `False` yazar.
    """

    id: str
    type: Literal["commit", "pr", "issue", "branch"]
    actor: str
    branch: str | None
    files: list[str]
    ts: datetime
    ref: str
    actor_verified: bool = Field(
        default=True,
        description=(
            "actor alanı GERÇEK bir GitHub hesabıyla (commit author.login / "
            "webhook author.username) eşleşti mi? False => GitHub eşleştiremedi, "
            "ham git commit yazar adına (commit.author.name) düşüldü — bu "
            "kötü niyet değil, genelde yanlış/eksik git config anlamına gelir."
        ),
    )


Severity = Literal["low", "med", "high"]

# Modelin yazdigi metin -> bizim kelime dagarciğimiz. YALNIZ yazim/es-anlam
# farklari; anlam esnetilmez.
#
# NEDEN VAR (uretimde olculdu, 2026-07-29 — #327): judge `"High"` donduruyordu,
# `Detection.severity` ise `Literal["low","med","high"]` bekliyor. Pydantic
# reddediyor -> `JudgeUnavailableError` -> UC ardisik boyle hata devre kesiciyi
# aciyor -> kalan cifTLER hic DENENMEDEN dusuyor. Olculen bilanco:
#
#     degraded: {"judge_unavailable": 1509, "evaluated": 11}
#
# Yani tek bir harf buyuklugu farki tespit kapasitesinin ~%99'unu goturdu.
# Sistem yanlis davranmadi (yargiyi UYDURMADI, #252 sozlesmesi) — ama hatanin
# dogru ele alinmasi, hatanin olmamasindan ucuz degil.
_SEVERITY_ES_ANLAM: dict[str, Severity] = {
    "low": "low",
    "med": "med",
    # "medium" modelin DOGAL kelimesi; bizim kisaltmamiz "med". Prompt artik
    # dagarciği acikca yaziyor ama es-anlami burada da karsiliyoruz.
    "medium": "med",
    "high": "high",
}


def severity_normalize(ham: str) -> Severity:
    """Judge'in yazdigi severity metnini kanonik kelime dagarciğina cevirir.

    BILINMEYEN DEGER VARSAYILANA DUSMEZ — `ValueError` firlatir ve cagiran
    bunu `JudgeUnavailableError`'a cevirir. "Anlamadim" ile "dusuk oncelikli"
    ayni sey degil; `low`'a dusmek #252'de bilerek kaldirilan
    `_fallback_detection` fail-open'inin aynisi olurdu: degerlendirilememis
    bir cift, degerlendirilmis ve zararsiz bulunmus gibi gorunurdu.
    """
    anahtar = ham.strip().lower()
    if anahtar not in _SEVERITY_ES_ANLAM:
        raise ValueError(
            f"judge taninmayan severity yazdi: {ham!r} "
            f"(beklenen: {sorted(_SEVERITY_ES_ANLAM)})"
        )
    return _SEVERITY_ES_ANLAM[anahtar]


class Detection(BaseModel):
    id: str
    kind: Literal["conflict"] = "conflict"
    actors: list[str]
    branches: list[str]
    files: list[str]
    severity: Severity
    confidence: float
    rationale: str


class ScopeVerdict(BaseModel):
    ref: str
    verdict: Literal["in_scope", "drift", "non_goal_violation"]
    confidence: float
    evidence: "str | ScopeItemRef"
    match_none: bool = False
    judged_at: datetime | None = None
    signals: "Signals | None" = None
    # #330: bu karar TAM yetenekle mi üretildi? `None` = evet. Dolu ise
    # semantik retrieval kullanılamadı ve aday seçimi YALNIZ leksikal
    # eşleşmeyle yapıldı — karar hâlâ gerçek ama zemini dar. Eskiden bu
    # durumda uç 503 dönüyordu (hiç karar yok); şimdi karar üretiliyor ama
    # eksiklik SESSİZ GEÇMİYOR (radar `degraded` şeridiyle aynı ilke —
    # "temiz" ile "temiz diyemiyoruz" karıştırılmaz).
    degraded: str | None = None


class ScopeItemRef(BaseModel):
    quote: str
    item_id: str | None = None
    section: Literal["goal", "in_scope", "non_goals"] | None = None
    line: int | None = None


class Signals(BaseModel):
    files: list[str]
    matched_text: str | None = None


class ScopeCandidate(BaseModel):
    evidence: ScopeItemRef
    similarity: float


class ScopeJudgement(BaseModel):
    verdict: Literal["in_scope", "drift", "non_goal_violation"]
    confidence: float
    evidence_index: int | None = None


class ScopeSubject(BaseModel):
    ref: str
    text: str
    files: list[str] = Field(default_factory=list)
    sprint: str | None = None


class ScopeCurrent(BaseModel):
    goal: str = Field(min_length=1)
    in_scope: list[str] = Field(min_length=1)
    non_goals: list[str]
    version: str = Field(min_length=1)
    frozen_at: datetime
    ref: str = Field(min_length=1)
    commit_sha: str = Field(pattern=r"^[0-9a-fA-F]{7,64}$")


class BoardCard(BaseModel):
    task_id: str
    title: str
    status: Literal["backlog", "todo", "in_progress", "in_review", "done"]
    assignee: str | None
    ref: str | None


class ActorRef(BaseModel):
    """Açık aktör tipi (#32/#52) — kontrat: docs/sprint2-kontratlar.md Ek B1."""

    handle: str
    type: Literal["human", "agent"]
    responsible: str | None = None


class PresenceEntry(BaseModel):
    """.harness/active/* projeksiyonu (#32/#52) — kontrat: Ek B1."""

    actor: ActorRef
    module: str
    task: str | None
    branch: str | None
    since: datetime


class GraphNode(BaseModel):
    """GET /graph düğümü (#104) — kontrat: docs/sprint2-kontratlar.md Ek A
    (S2 Ek A, #106 ile donmuş).

    `actor_verified` (#296, T-296) TEK katkı: additive + varsayılanlı, aynı
    desenle donmuş `NormalizedEvent`e eklenen alan gibi (bkz.
    docs/sprint3-kontratlar.md Ek G). Yalnız `type="actor"` düğümlerinde
    ANLAMLIDIR — `type="module"` düğümlerinde varsayılan değerde kalır
    (kontrol edilmez, UI de bakmaz).
    """

    id: str
    type: Literal["actor", "module"]
    weight: int
    actor_verified: bool = Field(
        default=True,
        description=(
            "Yalnız type='actor' için anlamlı. Bu aktörün bu penceredeki "
            "olaylarından EN AZ BİRİ GERÇEK bir GitHub hesabıyla eşleşti mi? "
            "(bkz. engine/graph.py build_touch_graph - toplama kuralı ve "
            "gerekçesi orada.) False yalnızca aktörün TÜM olayları eşleşmediğinde."
        ),
    )


class GraphEdge(BaseModel):
    """Aktör -> modül kenarı (#104). module = path'in ilk 2 segmenti (HESAPLANIR)."""

    actor: str
    module: str
    count: int
    last_ts: datetime
    is_active_declared: bool


class TouchGraph(BaseModel):
    """GET /graph çıktısı (#104) — sıfır LLM, saf NormalizedEvent + active/ aggregation."""

    window_days: int
    nodes: list[GraphNode]
    edges: list[GraphEdge]


CitationType = Literal["scope", "task", "decision", "event", "pr"]


class LineRange(BaseModel):
    start: int = Field(ge=1)
    end: int = Field(ge=1)


class Citation(BaseModel):
    type: CitationType
    ref: str
    quote: str
    url: str | None = None
    range: LineRange | None = None
    n: int | None = Field(default=None, ge=1)


class SearchReceipt(BaseModel):
    type: CitationType
    count: int = Field(ge=0)


class NearestRef(BaseModel):
    type: CitationType
    ref: str


class QueryResult(BaseModel):
    answer: str
    citations: list[str | Citation]
    as_of: datetime
    last_commit: str
    window: str | None = None
    confidence: Literal["low", "medium", "high"]
    status: Literal["answered", "not_found"]
    searched: list[SearchReceipt]
    nearest: list[NearestRef]
    # #330: bu cevap TAM yetenekle mi üretildi? `None` = evet. Dolu ise
    # semantik retrieval kullanılamadı ve belge seçimi YALNIZ leksikal
    # eşleşmeyle yapıldı. Eskiden bu durumda uç 503 dönüyordu (hiç cevap
    # yok — canlıda 29 Tem'de üç örnek sorunun üçü de böyleydi); şimdi cevap
    # üretiliyor ama zeminin dar olduğu SESSİZ GEÇMİYOR. `ScopeVerdict.degraded`
    # ve `RadarResponse.degraded` ile aynı sözleşme.
    degraded: str | None = None


class QueryScanResult(BaseModel):
    """`/query/scan` — soru sorulmadan ÖNCE "ne aranabilir" ön-izlemesi (#319).

    `QueryResult.searched` ile AYNI `SearchReceipt` şeklini taşır ama sıfır
    LLM çağrısıyla üretilir (yalnız `source_port.load_query_corpus()` +
    sayım — `QueryService.scan()`). Tasarım paketindeki "Tarandı: kapsam ✓ ·
    14 görev ✓ · ..." şeridinin GERÇEK veri kaynağı budur.

    ÖLÇÜLMÜŞ SINIR (2026-07-29, `HarnessEventQuerySource.load_query_corpus`):
    corpus hiçbir zaman `type="decision"` belgesi ÜRETMEZ (`.harness/decisions/`
    okunmuyor) — yani `searched` içindeki decision sayısı HER ZAMAN 0'dır,
    "gerçekten 0 karar var" demek DEĞİL. Bu yüzden istemci (AskPage) bu
    alanı şeritte GÖSTERMEZ (uydurma sayı yerine gate — issue #319 "en önemli
    kural"); scope/task/event/pr sayıları gerçek ve gösterilebilir.
    """

    as_of: datetime
    last_commit: str
    searched: list[SearchReceipt]
    # Son `recent_event_window_hours` saatteki event+pr belge sayısı (tasarım
    # paketi "son 48 saat olayları" şeridi) — corpus'un TAMAMI değil, yalnız
    # bu pencere: event_limit=200 corpus'u zaten sona yakın olaylarla sınırlı
    # tutuyor (query_source.py), ama şeridin iddiası "yakın zaman" olduğu için
    # burada da AYNI 48 saatlik kesme uygulanır (iddia ile sayım eşleşsin).
    recent_events: int = Field(ge=0)
    recent_event_window_hours: int = Field(ge=1)
    # `recent_events` bir ALT SINIR mı? (#322 review, Semih) — corpus
    # `event_limit` ile kesildiyse VE kesilen kümede pencereden eski hiç olay
    # yoksa, pencerede daha fazla olay olabilir ama biz onları hiç ÇEKMEDİK.
    # O durumda sayı "en az N" demektir; istemci `N+` basar. `False` iken sayı
    # KESİN (kanıt: corpus'ta pencereden eski bir olay var → pencere tam
    # kapsanmış, çünkü olaylar `ts DESC` çekiliyor). "Sayıyı büyüt" değil
    # "belirsizliği görünür kıl" — decision sayısındaki gate'in aynı ilkesi.
    recent_events_capped: bool = False


class QueryDocument(BaseModel):
    id: str
    type: CitationType
    ref: str
    quote: str
    text: str
    url: str | None = None
    range: LineRange | None = None
    occurred_at: datetime | None = None


class QueryCorpus(BaseModel):
    documents: list[QueryDocument]
    last_commit: str
    # Olay belgeleri kaynakta `event_limit`'e DAYANDI mı (#322 review, Semih):
    # `True` ise DB'de daha eski olaylar var ama corpus'a alınmadı. Kaynak
    # bunu bilir, `QueryService` bilemez — bu yüzden veriyle birlikte taşınır.
    # `scan()` bunu tek başına DEĞİL, "pencereden eski olay gördüm mü" ile
    # BİRLİKTE değerlendirir (bkz. `QueryScanResult.recent_events_capped`).
    events_truncated: bool = False


class QueryJudgement(BaseModel):
    answer: str
    citation_refs: list[str]
    confidence: Literal["low", "medium", "high"]
