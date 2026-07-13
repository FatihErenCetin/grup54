# Sprint-2 Kontratları (girdi → çıktı)

> **Amaç:** Bileşenlerin arayüzlerini *önce* sabitlemek → herkes **stub**'a karşı paralel çalışır, kimse kimseyi beklemez. Kontrat değişirse buraya PR aç + ekibe haber ver.

## İlke: kontrat-önce, paralel geliştirme

İki tür kontrat var, ikisi de "bekleme"yi ortadan kaldırır:

1. **HTTP (FastAPI ↔ frontend):** endpoint'ler Pydantic modellerden **`shared/openapi.json`** üretir → frontend TS client *otomatik* (codegen). Frontend, backend bitmeden client'ı üretip **mock veriyle** çalışır.
2. **Python Protocol (katmanlar arası):** her bağımlılık bir `Protocol` arkasında → **fake adapter** ile stub'lanır. AI judge'ı gerçek Gemini olmadan, ingest gerçek GitHub olmadan test edilir.

```
frontend ──HTTP(openapi)──> FastAPI router ──Protocol──> engine core ──Protocol──> adapters (Gemini/GitHub/DB)
   (mock client)              (#14)            (#17,18)       (EmbeddingsPort…)        (#15,16)
```

---

## 1. Çekirdek veri modelleri (`src/shared/models.py`) — herkesin uzlaştığı JSON

Bu modeller hem FastAPI yanıtı (JSON) hem Python tipi. **Bunları ilk gün dondururuz** (GATE 2, #14).

```python
from pydantic import BaseModel
from datetime import datetime
from typing import Literal

class NormalizedEvent(BaseModel):       # ingest çıktısı (#16)
    id: str
    type: Literal["commit", "pr", "issue", "branch"]
    actor: str                          # github handle
    branch: str | None
    files: list[str]                    # dokunulan path'ler
    ts: datetime
    ref: str                            # PR# / sha

class Detection(BaseModel):             # GET /radar öğesi (#17)
    id: str
    kind: Literal["conflict"] = "conflict"
    actors: list[str]                   # çarpışan kişiler
    branches: list[str]
    files: list[str]                    # kesişen path'ler
    severity: Literal["low", "med", "high"]
    confidence: float                   # 0..1 (judge)
    rationale: str                      # LLM-judge gerekçesi (TR)

class ScopeVerdict(BaseModel):          # GET /scope/check öğesi (#31, S3)
    ref: str                            # PR ref
    verdict: Literal["in_scope", "drift", "non_goal_violation"]
    confidence: float
    evidence: str                       # alıntılanan scope satırı

class BoardCard(BaseModel):             # GET /board öğesi (S3)
    task_id: str                        # "T-17"
    title: str
    status: Literal["backlog", "todo", "in_progress", "in_review", "done"]
    assignee: str | None
    ref: str | None                     # PR/issue
```

---

## 2. Port'lar (`Protocol`) — paralel çalışmanın dikişleri

Her port bir **arayüz**. Gerçek adapter ile fake adapter aynı imzayı uygular → test + paralel.

```python
from typing import Protocol

class GitHubPort(Protocol):             # impl: #16 · fake: fixtures
    def fetch_events(self, since: datetime) -> list[NormalizedEvent]: ...
    def compare(self, base: str, head: str) -> list[str]: ...   # değişen dosyalar

class EmbeddingsPort(Protocol):         # impl: #15 (Gemini) · fake: hash-vector
    def embed(self, texts: list[str], task_type: str) -> list[list[float]]: ...

class VectorIndexPort(Protocol):        # impl: #15 (FAISS/pgvector)
    def upsert(self, id: str, vec: list[float], meta: dict) -> None: ...
    def query(self, vec: list[float], k: int) -> list[tuple[str, float]]: ...

class JudgePort(Protocol):              # impl: #17/#24 (Gemini) · fake: kural-tabanlı
    def judge_conflict(self, a: NormalizedEvent, b: NormalizedEvent,
                       overlap: list[str], sim: float) -> Detection: ...

class HarnessPort(Protocol):            # impl: #13 (GATE 1)
    def read_scope(self, sprint: str) -> dict: ...
    def read_tasks(self) -> list[dict]: ...      # board'ın tek kaynağı (#13 ile eklendi)
    def read_active(self) -> list[dict]: ...
    def write_active(self, handle: str, decl: dict) -> None: ...   # yazar başına 1 dosya
```

---

## 3. HTTP endpoint'leri (FastAPI ↔ frontend kontratı)

| Method · Path | Girdi | Çıktı (JSON) | Issue |
|---|---|---|---|
| `GET /health` | — | `{status, mode}` | #14 |
| `GET /radar` | — | `{detections: Detection[], updated_at}` | #17, #25 |
| `GET /scope/check?ref=<pr>` | query | `ScopeVerdict` | #31 (S3) |
| `GET /board` | — | `{cards: BoardCard[]}` | S3 |
| `GET /query?q=<nl>` | query | `{answer: str, citations: str[]}` | S3 |
| `GET /graph?window_days=14` | query (varsayılan 14) | `TouchGraph` | #104 *(Ek A — S2 çekme adayı)* |

Frontend (#20) bu şemayı `openapi.json`'dan üretir → `apiClient.GET("/radar")` tip-güvenli. Backend bitmeden **mock server** (aynı şema) ile çalışılır.

---

## 4. Pratik: paralel çalışma reçetesi

- **GATE 2 (#14) ilk gün** `shared/models.py` + port imzalarını + `openapi.json`'ı yayınlar → **kontratlar donar.**
- **Frontend (#19-21):** `openapi.json`'dan client üretir, **mock veriyle** radar sayfasını yapar — backend'i beklemez.
- **AI (#17,18):** `JudgePort` + fixtures ile dedektörü yazar — gerçek Gemini'yi sonra bağlar.
- **Ingest (#16):** `GitHubPort` impl — fake adapter'la diğerleri test eder.
- **Entegrasyon:** herkes kendi fake'ini gerçek adapter'la değiştirir; imza aynı olduğu için kırılmaz.

> **Kural:** kontrat değişikliği = bu dosyaya PR + daily'de duyuru. Sessizce imza değiştirme (birinin stub'ını kırarsın).

---

## Ek A (7 Tem) — `GET /graph`: aktör×modül dokunma grafı (#104, S2 çekme adayı)

> **Yalnız EKLEME** — yukarıdaki donmuş imzalara dokunulmadı. #104/#105 **S2 taahhüdünde değil, çekme adayı** (kural issue'larda): kim ne zaman çekerse çeksin kontrat şimdiden donuk olsun diye buraya işlendi (D-33). Sıfır LLM — saf `NormalizedEvent` + `active/` aggregation.

```python
class GraphNode(BaseModel):             # GET /graph düğümü (#104)
    id: str                             # "enes" | "backend"
    type: Literal["actor", "module"]
    weight: int                         # toplam dokunuş sayısı

class GraphEdge(BaseModel):             # aktör→modül kenarı
    actor: str                          # github handle
    module: str                         # path'in ilk 2 segmenti (HESAPLANIR, şemaya yazılmaz)
    count: int                          # penceredeki event sayısı
    last_ts: datetime
    is_active_declared: bool            # .harness/active/ beyanı var mı

class TouchGraph(BaseModel):            # GET /graph çıktısı
    window_days: int
    nodes: list[GraphNode]
    edges: list[GraphEdge]
```

- **Frontend (#105):** bu şemadan üretilen client ile ısı matrisi — mock `TouchGraph` ile backend'i beklemeden başlanabilir (yukarıdaki reçetenin aynısı).
- **Format notu:** node-link JSON + `weight`'li kenar = D3 uyumlu konvansiyon.

---

## Ek B (9 Tem) — Tasarım turu kontrat ekleri (S3 build ön-koşulları)

> **Kapsam beyanı:** Çoğu madde salt-ekleme; **B3 ve B4'te iki İMZA REVİZYONU** var (geriye-dönük union'la yumuşatılmış) — kural gereği bu PR + daily duyurusuyla geliyor. Bunlar **S2 taahhüdü DEĞİL**: 14 yüzeylik tasarım turunun (design/ensemble.pen) çıkardığı, ilgili S3 build'i başlamadan donması gereken şekiller. 🔴 = o ekranın bloklayıcısı. Taslak 6-denetçili adversarial doğrulamadan geçti.

### B1 · Radar ekleri (#21/#25 — 🟠 S2'de mock, S3'te canlı)

```python
class Detection(BaseModel):
    ...                                     # mevcut alanlar AYNEN
    first_seen_at: datetime | None = None   # yaş; None ise frontend ilk-poll zamanı kullanır
    status: Literal["active", "resolved"] = "active"   # "Çözüldü" sekmesi + regressed rozeti
    resolved_at: datetime | None = None

class ActorRef(BaseModel):                  # handle-soneki sezgisi yerine açık tip (kaynak:
    handle: str                             # .harness/active/* front-matter'ı zaten taşıyor)
    type: Literal["human", "agent"]
    responsible: str | None = None          # agent ise sorumlu insanın handle'ı (pair)

class PresenceEntry(BaseModel):             # .harness/active/* projeksiyonu
    actor: ActorRef
    module: str
    task: str | None                        # "T-12" — presence şeridinde gösterilir
    branch: str | None
    since: datetime                         # beyan zamanı (stale gösterimi + beyan yaşı)

# GET /presence → {entries: PresenceEntry[], updated_at}
```

*Adlandırma notu:* donmuş modellerde `actor: str` (NormalizedEvent, GraphEdge) AYNEN kalır ve `ActorRef.handle`'a eşlenir — yeni tipler zengin biçimi kullanır. *Blob-link notu:* `files[]` düz path'tir; GitHub linkini frontend, workspace repo bağlamından kurar.

### B2 · Board eki (S3 board build — 🔴)

```python
class BoardCard(BaseModel):
    ...                                     # mevcut alanlar AYNEN
    last_event: LastEvent | None = None     # provenance satırı + sıralama + varış vurgusu + yaş

class LastEvent(BaseModel):
    type: Literal["pr_merged", "pr_opened", "issue_opened", "issue_closed", "branch_push"]
    actor: str
    at: datetime
```

*Enum notu:* `NormalizedEvent.type` HAM olay tipidir (commit/pr/issue/branch); `LastEvent.type` olay+durum SEMANTİĞİdir (pr_merged = pr tipi + merged durumu) — bilinçli iki sözlük. *Polling:* öneri 10-15 sn; "N yeni" pili client-side diff ile.

### B3 · Scope ekleri (S3 #31 — 🔴 iki endpoint de bloklayıcı) — ⚠️ evidence İMZA REVİZYONU

```python
class ScopeItemRef(BaseModel):
    quote: str                              # birebir alıntı
    item_id: str | None                     # "NG-1" / "IS-3" — dosyadaki açık ID
    section: Literal["goal", "in_scope", "non_goals"] | None
    line: int | None

class ScopeVerdict(BaseModel):
    ...                                     # diğer alanlar AYNEN
    evidence: str | ScopeItemRef            # ⚠️ REVİZYON: düz str geriye-dönük kabul
    match_none: bool = False                # drift'te kapsamda karşılık YOK beyanı
    judged_at: datetime | None = None       # tekil yanıtta da zaman damgası
    signals: Signals | None = None

class Signals(BaseModel):                   # deterministik sinyaller kutusu + "kanıta git"
    files: list[str]
    matched_text: str | None

# GET /scope/current  → {goal, in_scope[], non_goals[], version, frozen_at, ref, commit_sha}
#   (commit_sha: donmuş dosyanın SHA'sı — #L14 evidence linki + v1→v2 kimlik kayması önlemi)
# GET /scope/verdicts → {verdicts: ScopeVerdict[], counts, judged_at}
```

*Konvansiyon (harness-schema notu):* `scope/sprint-N.md` maddeleri açık ID taşır (`NG-1:`, `IS-2:`). *Drift semantiği:* `evidence` = en yakın in_scope maddesi + `match_none=true`; hiç eşleşme yoksa açık beyan, sessiz boşluk değil. *Sürüm geçmişi:* endpoint gerektirmez — git log'dan türetilir.

### B4 · Ask ekleri (S3 #58 — 🔴 citations omurga) — ⚠️ citations İMZA REVİZYONU

```python
class Citation(BaseModel):
    type: Literal["scope", "task", "decision", "event", "pr"]
    ref: str                                # "T-31" / "D-07" / sha / "58" / "scope/sprint-2#L14"
    quote: str                              # birebir alıntı (hover + grep-doğrulanabilirlik)
    url: str | None = None                  # repo-içi tiplerde None olabilir (iç navigasyon)
    range: LineRange | None = None          # side-sheet satır vurgusu
    n: int | None = None                    # oturum-kararlı dipnot numarası

class LineRange(BaseModel):
    start: int
    end: int

# GET /query yanıtı (⚠️ citations REVİZYON — geriye-dönük union):
#   {answer: str,                           # içinde [cite:T-31] placeholder'ları (streaming-dayanıklı)
#    citations: list[str | Citation],
#    as_of: datetime, last_commit: str,     # tazelik damgası
#    window: str | None,                    # pencereli sorularda: "son 24 saat"
#    confidence: Literal["low","medium","high"],
#    status: Literal["answered","not_found"],
#    searched: [{type, count}],             # dürüst-red kanıt fişi
#    nearest: [{type, ref}]}                # onarım önerileri
```

### B5 · Events endpoint'i (S3 Activity — 🔴)

```
GET /events?since=<ISO>&before=<ISO|id>&limit=<n>&actor=<handle>&branch=<ad>
  → {events: NormalizedEvent[], has_more: bool}
```

- `NormalizedEvent` AYNEN (değişiklik yok). `before` cursor olarak id de kabul eder (aynı-saniye tie-break: id).
- `branch=` filtresi kart-başına hareket zincirini de karşılar (`?branch=T-42-...` → Board side-sheet zaman çizgisi).
- `type=` filtresi v1'de YOK — client-side (İnsan/ajan filtresi actor tipiyle çözülür).
- *Gün sınırı kuralı:* feed ayraçları ve daily penceresi = istemci YERELİNDE gece yarısı; `ts` UTC gelir, çeviri istemcide (tek yardımcı fonksiyon).

### B6 · Bilinçli ertelemeler (karar İSTEMEZ — kayıt için)

| Ertelenen | Not |
|---|---|
| `NormalizedEvent.parent_sha` | Git ağacının gerçek DAG hâli için; şerit-temelli görünüm bunsuz çalışır |
| `POST /feedback` + citation-tık telemetrisi | Yanlış-alarm/👎 sinyalleri S2-S3'te localStorage'da; yazma ucu S3-sonrası |
| `BoardCard.module` | v1 filtre assignee-only; modül filtresi S3-stretch |
| 7-gün tespit şeridi (Radar temiz-boş durumu) | Tarihsel sayım; S3 cila diliminde karar |
| `waiver{actor, reason, ref}` | "Muaf" rozeti S3 itiraz akışıyla birlikte |
| `confidence.basis` (Ask) | Açıklama metni; opsiyonel iyileştirme |
| SSE streaming (/query) | Tek-atım S3'te kalır; sahte-canlılık yasak |
| Auth/session kontratı (login/profil ekranları) | **#79 gate'li — bu ekin kapsamı DIŞI** (D-28) |

## Ek C (12 Tem) — Eval veri kontratı: `ConflictCase` (#26/#27 → #28/#29)

> Eval hattının veri sözleşmesi şimdiye dek örtüktü (#26'nın Pydantic modeli). #27 backtest dataset'i aynı şemayı paylaştığı için burada dondurulur. Kanonik kod: `tests/fixtures/conflict_corpus.py`.

```python
class ConflictCase(BaseModel):
    case_id: str
    event_a: NormalizedEvent          # AYNEN (tip genelde "pr" ya da "commit")
    event_b: NormalizedEvent
    overlap: list[str]                # kesişen dosya yolları
    sim: float | None                 # ⚠️ revizyon: float → float | None
    label: Literal["conflict", "no_conflict"]
    note: str                         # kaynak izi (PR #'ları, [ic-merge]/[ayni-yazar] etiketleri)
```

- **`sim` semantiği (tek revizyon):** `float` = kuratörlü fixture değeri — #26 korpusu embeddings olmadan geçit mantığını test edebilsin diye elle atanır ve runner geçite **girdi olarak verebilir**. `None` = backtest verisi (#27) — benzerliği **dedektör hesaplar**; dataset'e yazılmaz ki eval, ölçmesi gereken şeyi hazır cevap olarak taşımasın (veri sızıntısı). #26'nın mevcut satırları geriye dönük geçerli (hepsi float).
- **İki dataset, tek şema:** `tests/fixtures/conflict_corpus.jsonl` (kuratörlü, bilinen kenar durumlar) + `eval/datasets/backtest-grup54.jsonl` (gerçek tarih, gerçekçi dağılım). #28 runner'ı ikisini de tek kod yoluyla koşar.
- **Gri bölge dosyası** (`eval/datasets/backtest-grup54-gri.jsonl`) bu şemada DEĞİLDİR (`label` yerine `label_beklemede` taşır) ve **#28 v1 tarafından tüketilmez**. İnsan etiketi verilen vakalar ayrı `backtest-grup54-el-etiketli.jsonl` dosyasına (bu şemada) eklenir; otomatik üretilen dosyalara elle dokunulmaz (determinizm testi builder çıktısıyla bit-bit eşitlik arar).
- Üretim/determinizm kuralları: `eval/backtest/build_dataset.py` docstring'i + `eval/README.md`.

## Ek D (13 Tem) — Hata zarfı (#54): tüm endpoint'ler için tek sözleşme

> 500+stacktrace yasak. Her hata cevabı aynı zarfı taşır; kod `api/errors.py` (tek kaynak — `ERROR_RESPONSES` sabiti router'lara oradan yayılır, spec + üretilen TS client otomatik tiplenir).

```python
class ErrorEnvelope(BaseModel):
    error: str      # makine-okur kod (aşağıdaki tablo)
    message: str    # insan-okur TR — iç detay/stacktrace ASLA taşımaz
    status: int
```

| Durum | status | error kodu | Not |
|---|---|---|---|
| GitHub rate limit | 503 | `rate_limited` | + `Retry-After` başlığı |
| GitHub config eksik | 503 | `github_config` | ağa çıkmadan yakalanır |
| GitHub auth reddi | 502 | `github_auth` | kalıcı — retry edilmez |
| GitHub 5xx/bağlantı | 503 | `github_unavailable` | + `Retry-After` |
| Gemini geçici | 503 | `gemini_unavailable` | + `Retry-After` |
| Gemini kalıcı | 502 | `gemini_error` | |
| Beklenmedik | 500 | `internal` | mesaj **mod-bağımlı**: local=özet, hosted=generic; traceback yalnız log'da |

- `422` FastAPI'nin otomatik doğrulama cevabıdır (zarf dışı, dokunulmadı); `500` spec'e bilerek beyan edilmez.
- **CORS-on-error:** hata cevapları da `Access-Control-Allow-Origin` taşır (500 fallback'i Starlette'te CORS middleware'inin dışında koşar — başlık elle eklenir; #45/#150 dersi: yoksa tarayıcı gerçek hatayı "CORS error" diye gizler).
- Tüketiciler: frontend `usePolling` (tipli `error` — `components["schemas"]["ErrorEnvelope"]`), S3 MCP, curl/jüri.
