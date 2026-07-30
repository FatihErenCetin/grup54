---
title: Sprint 3 — go-live (canlıya alma) + web MVP'nin gerisi
status: frozen
owner: Fatih Eren Çetin (PO)
version: '1'
ref: .harness/scope/sprint-3.md
commit_sha: 18f846fba6b2c45c3374b61a69d43a328254d1a0
frozen_at: '2026-07-25T17:33:02+03:00'
goals:
- 'Go-live mekaniği: Fly.io backend + Vercel frontend canlıya alınır (docs/sprint3-kontratlar.md
  Ek A/F, docs/deploy-runbook.md)'
- 'Kalan API router''ları: /board · /events · /presence · /query · /scope · /graph
  (Ek B)'
- 'Store/pgvector''ün canlı bağlanması: hosted app-boot DI + DDL tek-kaynak (Ek C,
  #182/#183)'
- 'MCP okuma yüzü: who_is_touching + check_scope (read-first, Ek D, #32)'
- 'Üç frontend sayfası: Board · Ask · Activity + Actors/Radar ısı matrisi client-side
  (Ek E, #33/#105/#129)'
- 'Hosted demo sertleştirme: tek-repo pin + IP/rate cap + cached verdict (Ek F, #63)'
- 'Graph 4 görünüm modu (ısı matrisi · treemap · güç-yönlü · git şeridi) — #130;
  30 Tem''da PO kararıyla non_goals''tan kapsama ALINDI (D-64). Git ağacı gerçek
  commit DAG''ı DEĞİL: parent_sha kontratta yok, ok/dirsek çizilmiyor.'
non_goals:
- 'MCP write-back (declare_work yazma) — S3''te yalnız read, write-back stretch (Ek
  D sınırı, #32)'
- '"GitHub ile giriş" OAuth-user akışı — #79 GATE''li stretch, çekirdek eval (#17+#18)
  yeşil olmadan başlanmaz (D-28)'
- Dağıtık sayaç/cache (Redis) — Ek F5, bilinçli kapsam dışı (kapsam-sinirlari.md queue/worker
  yasağı)
- WebSocket/SSE push — polling sözleşmesi korunuyor, sahte-canlılık yasak (D-34, kapsam-sinirlari.md)
- 'Gerçek commit DAG''ı (parent_sha ile ebeveyn–çocuk okları / merge dirsekleri)
  — Ek-B B6 ertelemesi; git şeridi bu sınırı EKRANDA yazar, uydurmaz (D-64)'
- Full observability (Prometheus/Grafana/Sentry/OTel) · K8s/Helm/Terraform/canary
  — kapsam-sinirlari.md
type: scope
sprint: '3'
---
[.harness/scope/ — PO tarafından dondurulmuş (frozen) Sprint-3 kapsamı]

Amaç (docs/sprint3-kontratlar.md, satır 3): go-live (canlıya alma) + web MVP'nin gerisi — deploy mekaniği, kalan router'lar, store/pgvector'ün canlı bağlanması, MCP okuma yüzü ve üç frontend sayfası aynı anda, farklı kişilerde ilerliyor. Arayüzler sprint başında donduruldu (retro aksiyonu R2 · D-22: kontrat-önce paralelleşme).

Kaynak: GitHub milestone "Sprint 3" (#3, due 2026-08-02) + docs/sprint3-kontratlar.md (Ek A-F, FROZEN). Bu dosya #242 ile git'e alındı; içerik uydurulmadı — milestone + donmuş kontrat metninden birebir taşındı.
