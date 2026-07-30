---
type: decision
id: D-61
title: "Ürün ilk kez DIŞARIYA yazıyor — radar high-severity → PR'a uyarı yorumu (fail-closed, iki bayrak, idempotent)"
date: "2026-07-30"
status: accepted
---

## Bağlam — bugüne kadar %100 salt-okunurduk

29 Temmuz 2026'da ölçüldü: `src/backend/ensemble/integrations/github/adapter.py`
içinde **tek bir POST/PATCH yoktu**. Ensemble GitHub'ı okuyor, çakışmayı
buluyor, panoda gösteriyor — ama hiçbir şeye dokunmuyordu. Otomatik issue yok,
nudge yok, yorum yok. Bu düşüşün kaydı da yoktu; vizyon Sprint 3'e açıkça
"bir agentic aksiyon" yazdığı hâlde.

`#339` bu eşiği geçiyor: radar **`severity=high`** bir çakışma bulunca ilgili
**açık PR'a** gerekçelendirilmiş bir uyarı yorumu bırakılır (kim · hangi dal ·
kesişen dosyalar · judge gerekçesi · tespit kimliği).

## Karar

**Ürünün dışarıya yazan ilk yolu açılıyor — ama yazma yeteneği, guard'larıyla
birlikte tek bir paket olarak.** Guard'lar "sonra ekleriz" listesinde değil,
özelliğin tanımının parçası:

| Guard | Varsayılan | Ne garanti eder |
|---|---|---|
| `AGENTIC_ACTIONS_ENABLED` | **false** | Set edilmemiş bir kurulumda **tek bir GitHub çağrısı bile** yapılmaz. |
| `AGENTIC_ACTIONS_DRY_RUN` | **true** | Çalışır ama yazmaz; ne yazacağını loglar. |
| yalnız `severity=high` | — | `med`/`low` hiçbir şey yazmaz. Otomatik yorum ancak nadir olduğunda okunur. |
| idempotency | — | Yorum gövdesine makine-okunur işaret gömülür; yazmadan önce PR'ın mevcut yorumları taranır. Aynı tespit için **ikinci yorum asla**. |
| kapalı/merge edilmiş PR | — | İki bağımsız sinyal (`state` **ve** `merged`) "açık" demedikçe yazılmaz. |
| `AGENTIC_ACTIONS_MAX_PER_RUN` | **3** | Aşılan kısım **loglanır ve rapora girer** — sessizce kesilmez. |
| yazma hatası | — | Hiçbir koşulda "yazıldı" sayılmaz; `hata` olarak sayılır, ERROR loglanır, rapor `degraded` olur. |

**Gerçek yazma yalnızca üç şey birlikte varken olur:** `ENABLED=true` **ve**
`DRY_RUN=false` **ve** GitHub App'in `Pull requests: write` izni. Tek bir
bayrağı yanlışlıkla açmak yeterli değildir — iki bağımsız kasıt gerekir.

## ⚠️ Bu, donmuş kapsamdaki "MCP write-back" yasağı DEĞİL

`.harness/scope/sprint-3.md` (frozen) `non_goals` altında şu yazıyor:

> *"MCP write-back (declare_work yazma) — S3'te yalnız read, write-back stretch"*

**Bu karar o yasağı ihlal etmiyor; ikisi farklı yüzeyler.** Karıştırılmasın
diye ayrımı açıkça kayda geçiriyoruz:

| | Yasak olan (S3 non-goal) | Bu karar (#339) |
|---|---|---|
| Hedef | **`.harness/`** — repo içindeki kanonik ortak bağlam | **GitHub** — dışarıdaki PR konuşması |
| Yol | MCP `declare_work` → `active/<handle>.md` yazar | `GitHubPort.create_pull_request_comment` |
| Ne değişir | Ürünün **kendi doğruluk kaynağı** | Hiçbir kanonik kayıt — yalnızca bir yorum |
| Geri alınabilir mi | Kaynağı bozarsa etkisi kalıcı/yayılan | Yorum silinir, biter |

MCP yüzü **hâlâ read-first**: `who_is_touching` / `check_scope` okur, hiçbir
MCP aracı `.harness/`e yazmaz. `#339` `.harness/`e tek bir bayt yazmıyor.
Kapsam belgesinin ruhu ("ürün kendi doğruluk kaynağını sessizce değiştirmesin")
korunuyor. Ayrıca `AGENTS.md` kapsam disiplini agentic aksiyonu zaten
**STRETCH** olarak listeliyor — yasak değil, çekirdek yeşilken yapılacak iş.

## Neden bu tetikleyici, neden bu eylem

- **`severity=high`**: uyarının değeri nadirliğinden gelir. Her `med` çakışmaya
  yorum düşen bir bot ikinci günden itibaren okunmaz — ve okunmayan uyarı,
  hiç olmayan uyarıdan **kötüdür** (gürültüyü meşrulaştırır).
- **PR yorumu** (issue açmak / commit status yerine): çakışmanın *tam olarak
  yaşandığı yerde*, ilgili insanların zaten baktığı yüzeyde belirir. Yeni bir
  issue açmak, panoyu bizim kirletmemiz olurdu.
- **Çakışmanın iki tarafı da açık PR ise ikisine de yazılır** — uyarı tek
  tarafa düşseydi, diğer dalda çalışan kişi kendi PR'ında hiçbir şey görmezdi.

## Neden hata bir DEĞERE dönüşüyor (ve bu #252'ye aykırı değil)

`#252`'nin dersi "hatayı değere çevirme" değil, **"hatayı BAŞARI gibi görünen
bir değere çevirme"**dir. Aynı PR'ın kendi çözümü de `JudgeUnavailableError`'ı
bir değer olarak toplayıp `RadarResult.judge_unavailable` ile dışarı vermekti.
Burada da aynı desen: bir yazmanın patlaması kalan tespitleri düşürmez (bu,
#252'nin çözdüğü sorunun başka bir biçimi olurdu), ama sonuç **asla** `yazıldı`
sayılmaz — `hata` olarak sayılır, ERROR loglanır, çıkış kodu `1` olur.

## Neden HTTP ucu değil, `python -m ensemble.agentic_cli`

Bir `POST /agentic/...` ucu `openapi.json` + `schema.d.ts` yeniden üretimi
gerektirir ve teslime iki gün kala aynı üretilmiş dosyalara dokunan üç açık
PR'la çakışırdı. Modül girişi ise **üretim imajında olduğu gibi çalışır**:
`Dockerfile` `src/backend/`i kopyalar, `uv sync` `ensemble` paketini
`/app/.venv`e kurar, `PATH` zaten venv'i öne alır. (Bu repoda tersi bir tuzak
yaşandı: bir runbook adımı `make` çağırıyordu ama `Makefile` prod imajına hiç
kopyalanmıyordu — testler yeşildi, iş canlıya inemezdi.) Kanonik komut:

```bash
docker compose exec api python -m ensemble.agentic_cli
```

`make agentic` **yalnızca yerel** reçetedir. Tam sıra: `docs/deploy-runbook.md` §10.

Bu seçim `docs/kapsam-sinirlari.md`'nin YAPMA listesiyle de örtüşüyor:
*"❌ Write/CRUD REST (POST/PUT/DELETE board/task/scope)"*. `#339` hiçbir HTTP
yazma ucu **açmıyor** — ne board/task/scope'a, ne başka bir şeye. Ürünün kendi
API yüzeyi salt-okunur kalmaya devam ediyor.

**Doğrulandı (30 Tem, gerçek prod imajında):** `docker build` → imaj içinde
`python -m ensemble.agentic_cli --help` **çalışıyor**; `AGENTIC_ACTIONS_*` env
değişkenleri konteynerde okunuyor (`enabled: True` raporlandı); gerçek App
yokken `ENABLED=true, DRY_RUN=false` **çıkış kodu 2** ile reddediliyor. Aynı
imajda `make`/`uv` ikilileri ve `Makefile` **YOK** — yani runbook'a `make agentic`
yazılsaydı adım canlıda çalışmayacaktı (bu tuzak bu repoda bir kez yaşandı).

## Bedeli / kabul edilen risk

- **Public bir repoya yazıyoruz.** Yanlış pozitif bir "high" tespit, gerçek
  bir PR'da görünen yanlış bir uyarı demektir. Kabul edildi çünkü: (a) yorum
  gerekçesini ve tespit kimliğini taşır, insan 5 saniyede yargılayabilir;
  (b) tur başına en fazla 3; (c) tek tuşla kapanır (`ENABLED=false`).
- **İzin genişliyor.** App'e `Pull requests: write` verilmesi gerekiyor (PO
  panelden verecek). İzin gelene kadar kod kuru çalışmada tam çalışır ve
  testler geçer; canlı yazma yalnız bayraklar **ve** izin birlikte varken olur.
- **Canlı GitHub'a test yazılmadı** — bilinçli. Doğrulama fake adapter +
  `httpx.MockTransport` (gerçek REST uç yolları, 403/304/sayfalama dahil) ile
  yapıldı: `tests/unit/test_agentic_action.py`.
