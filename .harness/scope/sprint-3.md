---
title: Sprint 3 — go-live (canliya alma) + web MVP'nin gerisi
status: frozen
owner: Fatih Eren Cetin (PO)
version: '1'
ref: main
commit_sha: 5cf20097ed30a95162c5b2e8775c305a74792f1a
frozen_at: '2026-07-25T17:33:02+03:00'
goals:
- 'Go-live mekanigi: Fly.io backend + Vercel frontend canliya alinir (docs/sprint3-kontratlar.md
  Ek A/F, docs/deploy-runbook.md)'
- 'Kalan API router''lari: /board · /events · /presence · /query · /scope · /graph
  (Ek B)'
- 'Store/pgvector''un canli baglanmasi: hosted app-boot DI + DDL tek-kaynak (Ek C,
  #182/#183)'
- 'MCP okuma yuzu: who_is_touching + check_scope (read-first, Ek D, #32)'
- 'Uc frontend sayfasi: Board · Ask · Activity + Actors/Radar isi matrisi client-side
  (Ek E, #33/#105/#129)'
- 'Hosted demo sertlestirme: tek-repo pin + IP/rate cap + cached verdict (Ek F, #63)'
non_goals:
- 'MCP write-back (declare_work yazma) — S3''te yalniz read, write-back stretch (Ek
  D siniri, #32)'
- '"GitHub ile giris" OAuth-user akisi — #79 GATE''li stretch, cekirdek eval (#17+#18)
  yesil olmadan baslanmaz (D-28)'
- Dagitik sayac/cache (Redis) — Ek F5, bilincli kapsam disi (kapsam-sinirlari.md queue/worker
  yasagi)
- WebSocket/SSE push — polling sozlesmesi korunuyor, sahte-canlilik yasak (D-34, kapsam-sinirlari.md)
- 'Graph ek gorunum modlari (git agaci · guc-yonlu · treemap) — #130, ayrica S3-stretch
  etiketli'
- Full observability (Prometheus/Grafana/Sentry/OTel) · K8s/Helm/Terraform/canary
  — kapsam-sinirlari.md
type: scope
sprint: '3'
---
[.harness/scope/ — PO tarafindan dondurulmus (frozen) Sprint-3 kapsami]

Amac (docs/sprint3-kontratlar.md, satir 3): go-live (canliya alma) + web MVP'nin gerisi — deploy mekanigi, kalan router'lar, store/pgvector'un canli baglanmasi, MCP okuma yuzu ve uc frontend sayfasi ayni anda, farkli kisilerde ilerliyor. Arayuzler sprint basinda donduruldu (retro aksiyonu R2 · D-22: kontrat-once parallellesme).

Kaynak: GitHub milestone "Sprint 3" (#3, due 2026-08-02) + docs/sprint3-kontratlar.md (Ek A-F, FROZEN). Bu dosya #242 ile git'e alindi; icerik uydurulmadi — milestone + donmus kontrat metninden birebir tasindi.
