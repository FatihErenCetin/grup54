---
type: decision
id: D-60
title: "Board kart kümesi artık `.harness/tasks/` ile sınırlı değil — GitHub issue'ları da kart üretir"
date: "2026-07-30"
status: accepted
---

## Bağlam

#331, "kendiliğinden **dolan** board" vaadinin karşılanmadığını **ölçtü**
(29 Tem):

| Ölçüm | Değer |
|---|---|
| Repodaki issue | ~150 |
| Board'daki kart | **22** (= `.harness/tasks/*.md` dosya sayısı) |
| Kartı gerçekle çelişen | **9 / 22** |

O günün gerçek işleri (`T-319`/`T-324`/`T-327`) `apply_transitions` tarafından
`unmatched` diye loglanıp panoya **hiç** düşmüyordu. Sebep bir bug değil,
yazılı bir **kural**dı: `internal/grup54_dizin_yapisi.md` §7,
`.harness/tasks/T-<id>.md`'yi "board'ın **tek** kaynağı" ilan ediyordu.
Kart açmak elle bir dosya commit'lemeyi gerektiriyordu — yani panonun
"kendiliğinden dolması" fiilen imkânsızdı.

## Karar

**Kart KİMLİĞİ iki kaynaktan gelir: `.harness/tasks/` VE gerçek GitHub
issue'ları.** Çakışmada **`.harness` kazanır** (§7 bozulmadı).

Uygulama (iki yol, tek kural):

| Yol | Ne yapar |
|---|---|
| `store/rebuild.py::rebuild_projection` | `.harness` tohumlarını kurar; ardından `github.fetch_backfill_resources()`'un getirdiği ham issue'lardan **karşılığı olmayanlar** için `TaskProjectionRow.from_github_issue` ile kart açar |
| `api/routers/webhook.py` → `Projector.upsert_issue_cards` | canlı `issues` webhook'unda aynı şeyi tek issue için yapar (yeni issue **anında** kart olur) |

Sınır **korundu**: `apply_transitions` hâlâ **kart UYDURMAZ**. Bir geçişin
elinde yalnız `task_id` vardır (başlık/assignee yok); kart ancak **gerçek
issue nesnesi** elde varken açılır. Karşılığı olmayan geçişler eskisi gibi
`orphan_transitions` olarak **sayılır ve görünür kalır** (ölçüm: 12 satır —
hepsi `T-<PR numarası>` biçiminde yanlış dal adları/`Closes` referansları).

## Neden bu yönde

1. **Vaadin kendisi.** "Kendiliğinden dolan board", kart açmak için elle
   dosya commit'lemeyi gerektiriyorsa vaat değil, ödevdir.
2. **`.harness` kanonikliği bozulmuyor.** `.harness` **içerik** (başlık,
   assignee, tohum durum) için hâlâ üstün; GitHub yalnızca `.harness`'in
   **sessiz kaldığı** yerleri doldurur. Aynı `task_id` için dosya varsa
   GitHub'ın başlığı satıra hiç yazılmaz (test: `test_rebuild_HARNESS_KAZANIR_*`).
3. **Uydurma yok.** GitHub kaynaklı kartın başlığı/assignee'si GitHub'ın
   kendi verisidir; durumu ise tohumdan (`backlog`) değil, aynı anlık
   görüntüden türeyen **geçişlerden** katlanır. "Kapalı issue'yu doğrudan
   `done` tohumla" kestirmesi bilerek YAPILMADI — o, durumu
   `task_status_events` günlüğünden koparıp kanıtsız bir `done` üretirdi.
4. **Şema değişmedi.** Yeni kolon/migration/kontrat **yok** (`openapi.json`
   bit-bit aynı). Kartın kaynağı var olan `ref` alanında görünür
   (GitHub kaynaklı = `#<numara>`, `.harness` kaynaklı = genelde boş) ve
   `rebuild_projection` dönüşünde `tasks_from_harness` / `tasks_from_github`
   diye **sayılır**.

## Ölçüm (uçtan uca, gerçek GitHub verisi — 2026-07-30)

`GitHubAdapter` → `rebuild_projection` → `BoardService.get_board()`:

```
tasks=155  tasks_from_harness=22  tasks_from_github=133
backfill_transitions=316  orphan_transitions=12
board: 155 kart | source=ingest

GitHub durumuyla karşılaştırma:  DOĞRU=155  YANLIŞ=0
(29 Tem'de yanlış olan 9 kartın 9'u da düzeldi)
```

Öncesi: 22 kart · 9 yanlış · 131 kartsız issue.

## Kabul edilen açık

- GitHub kaynaklı bir kartın **başlığı/assignee'si** canlı yolda
  tazelenmez (`upsert_issue_cards` var olan satıra **dokunmaz** —
  `.harness` üstünlüğünü basit tutmak için). Başlık değişikliği bir sonraki
  `make rebuild`'de yansır. Bunun canlı-yol tazelemesi istenirse kartın
  kaynağını (harness mı github mı) **açıkça** taşıyan bir kolon gerekir;
  bugün o kolon yok ve `ref` üzerinden çıkarım yapmak kırılgan olurdu.
- `.harness/tasks/` dosyaları **silinmedi**: dosyası olan 22 iş için
  başlık/assignee hâlâ oradan gelir (§7 aynen geçerli).

## İlgili

- Issue: #331 · dal `T-331-board-gecmis-ve-tazelik`
- Kod: `src/backend/ensemble/store/rebuild.py` · `engine/projector.py` ·
  `store/models.py::from_github_issue` · `ports.py::BackfillResources`
- Test: `tests/unit/test_rebuild.py` · `tests/unit/test_webhook.py`
