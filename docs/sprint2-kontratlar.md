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
