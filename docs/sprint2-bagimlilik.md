# Sprint 2 — Bağımlılık Haritası & Yürütme Sırası

> **Amaç:** Kim neyi **şimdi** başlatabilir, ne neyi bekler — tek bakışta. Kaynak: issue gövdeleri + `docs/sprint2-kontratlar.md`. Kanonik durum GitHub'dadır; bu doküman *sıralama rehberi*dir.
> **Revizyon: 13 Tem 2026 (sprint-ortası tazeleme, #153)** — 25/37 issue kapandı ✓; #151 (canlı kablolama) ve #146 (PR triyajı) eklendi; #17/#21/#146 PR aşamasında. İlk sürüm: 8 Tem (#108).
> **Okuma:** düz ok `A --> B` = *B, A bitmeden canlıya çıkamaz* · kesik ok `A -.-> B` = *yumuşak bağımlılık: B mock/fixture ile beklemeden başlar, canlı için A gerekir* (kontrat-önce ilkesi, D-22). Gri düğüm = kapandı (yalnız açık işlere zemin olanlar grafikte; tam liste §5).

## 1. Görsel harita (GitHub bu diyagramı render eder)

```mermaid
graph LR
  classDef semih fill:#5b8def,color:#fff,stroke:#2f5bb7
  classDef esma fill:#9d5bde,color:#fff,stroke:#6b2fb7
  classDef enes fill:#2e9e6b,color:#fff,stroke:#1d6b47
  classDef fatih fill:#de8f3c,color:#fff,stroke:#a8641d
  classDef done fill:#3a3f45,color:#9aa3ad,stroke:#565e66

  subgraph SIMDI["🔴 BUGÜN kritik (13 Tem)"]
    I17["#17 ⭐ Dedektör — PR #148 🟡 düzeltmede"]:::semih
    I28["#28 Eval runner — kod lokalde, PR bekleniyor"]:::enes
  end

  subgraph EVAL["📏 Eval/kalibrasyon"]
    I26["#26 ✓ Korpus"]:::done
    I27["#27 ✓ Backtest dataset"]:::done
    I29["#29 Threshold sweep (+aynı-yazar ekseni)"]:::enes
    I30["#30 CI precision-gate"]:::enes
    I18["#18 ⭐ Kalibrasyon (sprint DoD)"]:::esma
  end

  subgraph CANLI["🔌 Canlıya bağlama"]
    I16["#16 ✓ GitHub ingest"]:::done
    I50["#50 ✓ Gemini adapter"]:::done
    I151["#151 Canlı kablolama: DI + eşikler config'ten"]:::esma
    I49["#49 Backfill (ilk N PR/commit)"]:::semih
  end

  subgraph AIALT["🧠 AI aşamaları (hepsi ✓)"]
    I22["#22 ✓ Jaccard"]:::done
    I23["#23 ✓ Cosine"]:::done
    I24["#24 ✓ Judge"]:::done
  end

  subgraph WEB["🖥️ Web"]
    I19["#19 ✓ Shell"]:::done
    I20["#20 ✓ TS client"]:::done
    I21["#21 Radar sayfası — PR #150 review'da (Esma)"]:::fatih
    I25["#25 ✓ /radar router"]:::done
    I45["#45 ✓ CORS"]:::done
  end

  subgraph DIGER["🛡️ Diğer"]
    I54["#54 Error envelope (ara işi)"]:::fatih
    I146["#146 PR triyajı — PR #147 re-review'da (Semih)"]:::fatih
    I124["#124 ⚙️ Harita oto-güncelleme botu (stretch)"]:::enes
    I15["#15 Embeddings — işi merge'li, issue AÇIK ❓"]:::semih
  end

  I22 --> I17
  I23 --> I17
  I24 --> I17
  I26 --> I28
  I27 --> I28
  I17 -.->|dedektör entegrasyonu| I28
  I28 --> I29
  I28 --> I30
  I29 --> I18
  I18 -.->|yeşil kanıt| I30
  I16 --> I151
  I50 --> I151
  I17 --> I151
  I16 --> I49
  I19 --> I21
  I20 --> I21
  I25 -.->|mock şimdi| I21
  I45 -.->|tarayıcıdan| I21
  I151 -.->|VITE_MOCK=0 canlı radar| I21
```

Renk = sahip: 🔵 Semih · 🟣 Esma · 🟢 Enes · 🟠 Fatih · ⬜ kapandı

**Kritik yol (kalan):** `#148 düzeltme (Semih) → #17 merge → #28 merge (Enes) → #29 → #18⭐ (Esma)` — sprint 19 Tem'de bitiyor, bu zincir **5 iş günü değil 6 takvim günü** içinde kapanmalı. Paralel demo şeridi: `#17 → #151 (Esma) → canlı radar` + `#150 merge → #21 kapanır`.

## 2. Dalgalar — bugünden itibaren (13 Tem)

| Dalga | Issue'lar | Not |
|---|---|---|
| **D0 — ŞİMDİ, paralel** | Semih: **#148 düzeltmeleri** (4 küçük istek — kritik yol!) · Enes: **#28 PR'ını aç** (kod hazır; main'i çek, `conflict_corpus.py`'de main'inkini al) · Esma: #149 atıf düzeltmesi+merge → #150 review · Fatih: #54 | #28 PR'ı #17'yi *beklemeden* açılabilir (dedektör entegrasyonu #17 merge'üyle tamamlanır — kesik ok) |
| **D1 — #148 merge sonrası** | #17 kapanır → Enes #28'i finalize/merge · Esma #151 (canlı DI — eşikler Settings'e) | #151'in sert ön-koşulları (#16 ✓ #50 ✓) hazır; anlamlı canlı radar için #17 gerekir |
| **D2** | Enes: #29 (aynı-yazar ekseni dahil — #29'daki veri notu) + #30 · Fatih: #150 merge → #21 kapanır · Semih: #49 (sığarsa — ❓) | |
| **D3 — kapanış (18-19 Tem)** | Esma: **#18⭐** (eval yeşil = DoD) + sprint 6-başlık raporu | DoD kapısı: eval kabul edilebilir FP göstermeden "kusursuz radar" iddiası yok |

## 3. Kişi bazlı sıra (kalan işler)

| Kişi | Sıra (→ = sonra) | Bekleme notu |
|---|---|---|
| **Semih** | **#148 düzeltmeleri (BUGÜN)** → #17 merge → #49 (❓ sığarsa) → #147 re-review (küçük) | Kritik yol hâlâ onda; #148'in 4 isteği küçük (conflict tek dosya/import + 1 satır default + try/except + TODO). #15'in issue'su kapatılmalı ❓ |
| **Esma** | #149 düzelt+merge → #150 review → **#151** → **#18⭐** | Sprint yine onun kapanışıyla bitiyor; #151 orta boy (DI + Settings eşikleri), #18 eval çıktısına bağlı |
| **Enes** | **#28 PR'ını aç (BUGÜN)** → #17 entegrasyonu → #29 → #30 (+#124 stretch) | Kuyruk tamamen kendi elinde #28 PR'ıyla açılıyor; #124'e ancak #30 sonrası kapasite kalırsa |
| **Fatih** | #54 → #150/#147 merge'leri (onaylar gelince) → sprint raporu girdileri | S2 ana kuyruğu bitti; #54 bağımsız ara işi |

## 4. 🔴 Bugünün blocker'ları

| İş | Sahip | Aciliyet | Neden |
|---|---|---|---|
| **#148 düzeltmeleri** | Semih | **BUGÜN** | Kritik yolun tamamı bunun arkasında; her gün gecikme #28→#29→#18 zincirini sıkıştırıyor (sprint 19'da bitiyor) |
| **#28 PR açılışı** | Enes | **BUGÜN** | Kod lokalde hazır — tek engel main merge + conflict_corpus çözümü; PR açılmazsa review/entegrasyon süresi kapanışa sıkışır |
| **#149 düzelt+merge** | Esma | Bugün (5 dk) | Tek satır atıf düzeltmesi; daily kanıtı taze kalmalı |

## 5. Düz liste (issue · sahip · bağımlı olduğu · kilitlediği)

**Açık işler:**

| # | Sahip | Bağımlı olduğu | Kilitlediği (blocks) |
|---|---|---|---|
| 15 ❓ | Semih | işi merge'li (PR #134) | — (issue kapanışı bekliyor) |
| 17 ⭐ | Semih | #22✓ #23✓ #24✓ · PR #148 🟡 | #28-entegrasyon · #151 · sprint kalbi |
| 18 ⭐ | Esma | #26✓ #27✓ #28 #29 | sprint DoD |
| 21 | Fatih | #19✓ #20✓ · PR #150 review'da | demo (canlı: #151 sonrası bayrak) |
| 28 | Enes | #26✓ #27✓ (soft: #17) | #29 #30 #18 |
| 29 | Enes | #28 (+#29'daki aynı-yazar veri notu) | #18 |
| 30 | Enes | #28 (kanıt: #18) | CI koruması |
| 49 | Semih | #16✓ | demo dolu-radar (❓ S3'e ertelenebilir) |
| 54 | Fatih | — | hata deneyimi |
| 124 ⚙️ | Enes | — (stretch) | süreç otomasyonu |
| 146 | Fatih | PR #147 re-review'da (Semih) | atama otomasyonu |
| 151 | Esma | #16✓ #50✓ (anlamlı: #17) | canlı radar → #21-canlı · demo |
| 153 | Fatih | — | bu doküman (revizyon PR'ı) |

**Kapananlar ✓ (25):** #14 #16 #19 #20 #22 #23 #24 #25 #26 #27 #41 #45 #46 #47 #50 (kod/veri şeridi) · #106 #108 #112 #114 #116 #118 #120 #122 #127 (docs/süreç) · #126 (tasarım)

## ❓ PO'ya sorulacaklar

1. **#15 kapanışı:** T-15 işi PR #134 ile merge'lendi ama issue açık (PR gövdesi `Closes` dememiş olmalı) — kalan alt-iş yoksa kapatılmalı.
2. **#49 (backfill):** Semih'in kuyruğu #148+#17 ile dolu; #49 demo-dolu-radar için *nice-to-have* — sprint sonuna sığmazsa S3'e ertelensin mi?
3. **#124 (harita botu):** stretch — #30 sonrası kapasite kalmazsa S3'e taşınmalı mı?

> Güncelleme kuralı: sıra/bağımlılık değişirse bu dosyaya PR — kanonik issue durumu (atama dahil) her zaman GitHub'dadır (TDK). Sprint kapanışında bu haritadan "akış raporu" üretilecek (`/sprint-akis-raporu`).
