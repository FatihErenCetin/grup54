---
name: karar-drifti
description: Açık bırakılmış bir seçimin kayıt olmadan katılaşıp katılaşmadığını denetle (karar drifti). Kullanım - /karar-drifti [kapsam] (boşsa tüm repo). Rehber docs/karar-drifti-rehberi.md'dedir; denetim karar VERMEZ, işaretler ve D-NN taslağı önerir.
---

1. **`docs/karar-drifti-rehberi.md`'yi OKU** — sınıf tanımı (scope-drift'ten farkı), tespit adımları, katılık ölçeği, rapor formatı ve yanlış-pozitif kuralları oradadır (tek kaynak; burada tekrar yok).
2. `$ARGUMENTS` ile verilen kapsama rehberin **§3 adımlarını** sırayla uygula (`$ARGUMENTS` boşsa tüm repo). Açık PR dallarını da tara — `git show origin/<dal>:<yol>`, checkout ETME.
3. Her bulguyu §6'ya göre **çürütmeye çalış**; ayakta kalanları §5 formatında, `dosya:satır` kanıtıyla sun. Bulgu yoksa iki cümle yeter.
4. **Kararı ve kaydı insana bırak:** D-NN taslağını öner, karar loguna sen yazma; issue/doküman düzenleme de insanın.

> Aynı denetimi **`karar-arkeologu`** subagent'ı olarak da çağırabilirsin (`.claude/agents/karar-arkeologu.md`) — kapsam büyükse (tüm repo) ayrı bağlamda çalışır; adımlar birebir aynıdır.
