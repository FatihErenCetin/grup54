# Ensemble — Yol Haritası (Roadmap)

3 sprint · tam vizyon (FastAPI engine + AI çekirdek + web + MCP). Milestone = **sprint**, epic = **alan**. Canlı takip: [Issues](https://github.com/FatihErenCetin/grup54/issues) · [Board](https://github.com/FatihErenCetin/grup54/projects).

## Milestone'lar (sprintler)

| Milestone | Tarih | Odak |
|---|---|---|
| **Sprint 1** | 19 Haz–5 Tem | harness-dashboard ✓ · repo omurga ✓ · **foundation** (GATE 0/1) |
| **Sprint 2** | 6–19 Tem | **CORE:** GATE 2 + AI çekirdek (embeddings · ingest · **çakışma radarı** · eval) + web radar |
| **Sprint 3** | 20 Tem–2 Ağu | kabuk (board/ask) · scope-drift · MCP write-back · onboarding · hosted demo |

## Zaman çizelgesi

```mermaid
gantt
    title Ensemble — Sprint Zaman Çizelgesi
    dateFormat YYYY-MM-DD
    axisFormat %d %b
    section S1 · Foundation
    GATE0 scaffold #12          :done,    g0, 2026-06-30, 2d
    GATE1 harness-IO #13        :active,  g1, after g0, 3d
    section S2 · AI Çekirdek
    GATE2 pure core #14         :crit,    g2, 2026-07-06, 3d
    embeddings+store #15        :         e1, after g2, 3d
    GitHub ingest #16           :         e2, after g2, 3d
    ÇAKIŞMA RADARI #17          :crit,    d1, after e1, 4d
    eval/kalibrasyon #18        :crit,    ev, 2026-07-15, 3d
    frontend radar #19-21       :         fe, 2026-07-10, 6d
    section S3 · Kabuk + Deploy
    scope-drift #31             :         2026-07-20, 3d
    MCP read tools #32          :         2026-07-22, 3d
    board/ask/activity #33      :         2026-07-23, 6d
    hosted demo #34             :         2026-07-28, 5d
```

## Bağımlılık akışı (GATE'ler → paralel parçalar)

```mermaid
flowchart LR
    G0["GATE0\nscaffold #12"] --> G1["GATE1\nharness-IO #13"]
    G1 --> G2["GATE2\npure core + ports + openapi #14"]
    G2 --> EMB["embeddings\n+ VectorStore #15"]
    G2 --> ING["GitHub ingest\n+ App-auth #16"]
    EMB --> DET["⭐ çakışma\ndedektörü #17"]
    ING --> DET
    DET --> EVAL["⭐ eval +\nkalibrasyon #18"]
    G2 -.openapi.-> FE["frontend\nshell+client #19,20"]
    DET --> RADAR["radar\nsayfası #21"]
    FE --> RADAR
    G1 --> MCP["MCP read\ntools #32"]
    classDef crit fill:#ffe0e0,stroke:#d73a4a;
    class DET,EVAL crit;
```

> **Kritik yol** (kırmızı): foundation → çekirdek → **çakışma dedektörü → eval** → radar. Bu omurga demoable olunca AI değeri (35 puan) kanıtlanır. Geri kalan (frontend·ingest·MCP) **paralel** ilerler — kontratlar (↓) sayesinde kimse beklemez.

## Epic → öne çıkan story'ler

| Epic | Sprint 2 (commit) | Sprint 3 / stretch |
|---|---|---|
| **engine** (backend) | GATE2 #14 · ingest #16 | board+NL · scope-drift #31 |
| **ai** | embeddings #15 · çakışma #17 · eval #18 | model seçimi · scope-drift |
| **frontend** | shell #19 · client #20 · radar #21 | board/ask/activity #33 |
| **mcp** | — | who_is_touching/check_scope #32 · declare_work |
| **infra** | (GATE0/1 #12,13) | hosted demo #34 · onboarding |

## Kontratlar
Bileşenler arası girdi/çıktı arayüzleri (paralel çalışma için): **[`docs/sprint2-kontratlar.md`](docs/sprint2-kontratlar.md)**.

> Detaylı epic→story→task ağacı + araştırma: ekip-içi `internal/grup54_backlog.md`.
