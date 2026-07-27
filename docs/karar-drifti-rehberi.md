# Karar Drifti Rehberi — kayıt olmadan katılaşan seçimler (insan + AI ortak)

> **Ne zaman:** Sprint sınırında (planning/retro günü) · yeni bir issue'ya platform/sağlayıcı/kütüphane adı yazarken · *"biz buna ne zaman karar verdik?"* sorusu havada kalınca. AI aracına şunu de: *"`docs/karar-drifti-rehberi.md`'yi oku ve `<kapsam>` için karar drifti denetimi koş."* (Claude Code: `/karar-drifti [kapsam]` — boşsa tüm repo.)
> **Amaç:** Kimsenin *vermediği* ama artık *geri alınamayan* seçimleri, geri almak hâlâ ucuzken yakalamak.
> **Sınır:** Denetim **karar VERMEZ** — işaretler, kanıt sunar, D-NN taslağı önerir. Kararı ve kaydı insan yazar. Kayıt bugün ekip-içi/gitignored `internal/grup54_karar_logu.md` (D-NN) + `internal/grup54_vizyon_ve_karar_kaydi.md`'de (K/A) yaşıyor (bkz. `CLAUDE.md` "Public/özel ayrımı"); `.harness/decisions/` gelince taşınacak (karar_logu.md'nin kendi notu — bu rehberin §3 Adım 4'ü o zaman yol değiştirir, yöntem aynı kalır).

## 1. Karar drifti nedir — scope drift'ten farkı

|  | **scope drift** | **karar drifti** |
|---|---|---|
| Olan | iş, kabul edilmiş **kapsamın dışına** çıkar | iş **kapsam içindedir** ama açık bırakılmış bir **seçimi** sessizce kapatır |
| Kıyas ölçütü | `.harness/scope/sprint-N.md` (kabul edilmiş kapsam) | **karar kaydı** — `internal/grup54_karar_logu.md` (D-NN) · vizyon (K/A) |
| Sinyal | yeni iş ↔ kapsam metni uyuşmuyor | uygulama yüzeyinde alternatiflerden **tam biri** var, kayıtta seçim **yok** |
| Zarar | yapılmaması gerekeni yapmak | doğru işi yaparken **yanlış seçeneğe** kilitlenmek |
| Fark edilme | görece erken (kapsam metni sabit ve okunur) | **geç** — genelde geri dönüş pahalılaştıktan sonra |

**Mekanizma:** Kimse yalan söylemez, kimse kural çiğnemez. Bir seçim "A/B" diye açık yazılır; sonra biri A'yı içeren bir issue yazar; issue kabul edilir, kod yazılır, test yazılır, karar loguna A'yı **varsayan** başka kararlar eklenir. Hiçbir adımda *"B'yi ne zaman eledik?"* diye soran bir kapı yoktur. Mevcut kapılarımızın hiçbiri bu nesneye bakmaz: scope-drift kapsama bakar, review diff'e bakar, CI test koşar. Bu yüzden araç bir **diff aracı değil envanter aracıdır**: kıyaslanacak bir taban yoktur (yokluğa diff atılamaz) — önce açık seçimleri **listeler**, sonra her biri için *"kapanmış mı / kaydı var mı"* sorar.

## 2. Vaka — "Fly mi Render mı?" (birinci elden, 25 Tem 2026)

**Açık seçim:** `internal/grup54_vizyon_ve_karar_kaydi.md:99` — *"Deploy: backend **Fly/Render**, web Vercel"*. İki aday; gerekçe yok, sahip yok, son tarih yok.

**Kapanış — kimse fark etmeden:**

| Tarih | Artefakt | Ne oldu |
|---|---|---|
| 30 Haz 16:00 | issue **#34** başlığı: *"Hosted demo: **Fly** backend + Vercel + webhook"* | "Render" cümlenin dışında kaldı — **fiilî karar burada** |
| 30 Haz 17:40 | issue **#61**: *"Backend Dockerfile (**Fly imajı**)"* | seçim issue başlığına geçti |
| 20 Tem | issue **#181** kabul kriteri: *"`fly.toml`: [build] dockerfile, [http_service] internal_port=8000 …"* | seçim kabul kriterine girdi → artık **zorunlu** |
| 20 Tem | `Dockerfile:3` (ilk commit: *"feat: backend Dockerfile (Fly imaji)"*) · `Makefile:75` `flyctl deploy --config fly.toml` | koda girdi |
| 21 Tem | **D-39** (karar logu) | DB sağlayıcısına karar verirken Fly'ı **veri olarak** aldı — kayıt bile seçimi *varsaydı* |
| 24–25 Tem | PR **#236** `.github/workflows/deploy.yml` · PR **#240** `deploy/fly.db.toml` + `docs/deploy-runbook.md` + 2 test dosyası | CD + operatör rehberi |

**O gün ölçülen durum:** `Fly/Render` ikilisi doküman metninde hâlâ **12 kez** "açık" duruyordu (`.env.example:7` ve `docs/sprint3-kontratlar.md:67` dâhil) — ama uygulama yüzeyinde **Render'a ait tek bir artefakt yoktu**: ne `render.yaml`, ne `render.com`, ne bir issue, ne bir satır. Fly ise `eval/datasets/scope-corpus.json`'daki kapsam metnine kadar girmişti — yani geri alma, **eval ground-truth'unu** yeniden etiketlemek demekti.

**Kimse hata yapmadı.** Yalan yok, kapsam ihlali yok; Fly muhtemelen doğru tercihti. Eksik olan tek şey üç satırlık bir kayıttı: neden Fly, Render niye elendi, geri dönüş maliyeti ne. Vakanın kendisi **D-45**'te kayıtlı.

**Aynı gün ikinci perde — süreç kendini doğruladı:** D-45'i tetikleyen soru (*"Fly'ı kim seçti?"*) PO'yu gerçek gerekçeyi sorgulamaya itti; cevap **D-46**'da geldi: ekipte boşta bekleyen bir sunucu var, hosting maliyeti sıfıra iner → backend+DB fiilen **Fly'dan self-host'a taşındı** ("tek platform + özel ağ + tam kontrol" ilkesi aynen korunarak). Yani K3 katılığın "geri alma değil kaydı tamamla" tavsiyesi burada **ikisini birden** yaptı: kayıt tamamlandı (D-45) **ve** kayıt, kararın kendisini bir kez daha gözden geçirtti (D-46). İkisi çelişmez — asıl mesaj hâlâ aynı: *sessiz kapanış* olmasaydı bu soru 25 gün önce, artefaktlar çoğalmadan sorulurdu.

**Karşı örnek (sağlıklı hâli):** OAuth vs repo-token seçimi de aynı şekilde açıktı — ama **F-02** diye adlandırıldı, kuyrukta tutuldu, brainstorm edildi, **D-28**'de gerekçesiyle kapandı. Fark mekanizma değil, **kaydın kendisi**.

## 3. Tespit yöntemi (adım adım, çalıştırılabilir)

Kapsam = `$ARGUMENTS` (bir doküman, bir dizin, bir sprint); boşsa tüm repo.

**Adım 1 — Açık-seçim işaretçilerini topla.** İki tarama, sırayla:

> **Önce kaynakları doğrula.** `internal/` **gitignored**: senin makinende var,
> takım arkadaşında ve CI'da YOK. Aşağıdaki komutlar eksik yolda çökmez ama
> **eksik kaynağı rapora yazmak zorunludur** — taranmayan bir yer "temiz"
> sayılamaz (#257 bulgu 8).
>
> ```bash
> # Hangi kaynaklar GERÇEKTEN okunabiliyor? Raporun "kapsam" satırı bu.
> for k in internal docs README.md AGENTS.md .env.example; do
>   [ -e "$k" ] && echo "  okunabilir: $k" || echo "  EKSİK (taranmadı): $k"
> done
> ```

```bash
# (a) ikili aday kalıbı "A/B" — düşük gürültülü, ÖNCE bunu koş (yol adları filtreleniyor)
# `--include` + dizin: eksik dizinde zsh glob'u komutun TAMAMINI iptal etmez.
grep -rnoE --include="*.md" "\b[A-Z][A-Za-z]{2,}/[A-Za-z][A-Za-z]{2,}\b" \
  internal docs README.md AGENTS.md .env.example 2>/dev/null \
  | awk -F: '{print $NF}' \
  | grep -vE "Sprint|Board|Screenshot|DailyScrum|Burndown|Meetings|General|README" \
  | sort | uniq -c | sort -rn

# (b) sözel işaretçiler — kalabalık; yalnız (a)'nın verdiği konunun ÇEVRESİNİ okumak için
grep -rniE "\b(TBD|aday|seçenek|açık nokta|netleşmedi|karar bekliyor|kuyruk|ya da|veya|vs\.?)\b" \
  internal/*.md docs/*.md
```

*(Bu repoda (a) çalıştırıldığında `Fly/Render` listenin en tepesinde çıkıyor — yöntem vakayı kendi başına buluyor.)*

**Adım 2 — Alternatifleri çıkar ve arama izlerine çevir.** Metindeki adı değil, **arayabileceğin izleri** yaz: paket adı, CLI adı, dosya adı, config anahtarı, alan adı.
`Fly → fly.toml · flyctl · fly.io · fly secrets` · `Render → render.yaml · render.com · RENDER_*`
⚠️ **Çıplak kelime kullanma:** `render` araması `scripts/bagimlilik_uret.py:363 render_block()`'u yakalar — ayırt edici iz seç.

**Adım 3 — Uygulama yüzeyinde her alternatifi ayrı ayrı ara.** Altı yüzey:

| Yüzey | Komut |
|---|---|
| Dosya adları | `git ls-files \| grep -iE "<iz>"` |
| Dosya içeriği | `git grep -ilE "<iz>"` |
| Issue/PR başlıkları | `gh issue list --state all --limit 300 --search "<iz>"` |
| Workflow / CI | `grep -rilE "<iz>" .github/` |
| Bağımlılıklar | `grep -iE "<iz>" pyproject.toml uv.lock src/frontend/package.json` |
| **Açık PR dalları** | `git ls-tree -r --name-only origin/<dal> \| grep -iE "<iz>"` *(checkout ETME; içerik: `git show origin/<dal>:<yol>`)* |

Açık PR dallarını atlamak **yanlış sonuç** verir: Fly/Render vakasında Fly artefaktlarının 5'i (`deploy.yml`, `deploy/fly.db.toml`, `deploy-runbook.md`, 2 test) hâlâ açık PR'daydı.

**Adım 4 — Kayıt kontrolü.**

```bash
# ÖNCE kaynak okunabilir mi? Boş çıktı iki AYRI şey demek olabilir:
#   (1) arandı, kayıt yok        -> hüküm verilebilir
#   (2) dosya hiç yok, aranamadı -> hüküm VERİLEMEZ
# Bu ayrım yapılmazsa `internal/` olmayan bir makinede (her takım arkadaşı,
# CI) kayıtlı bir karar 🚩 DRİFT diye bayraklanır (#257 bulgu 9 — ana kopyada
# aynı grep D-39/D-43/D-45/D-46'yı döndürüyor, yani kayıt VAR).
KAYNAKLAR="internal/grup54_karar_logu.md internal/grup54_vizyon_ve_karar_kaydi.md"
EKSIK=""
for f in $KAYNAKLAR; do [ -f "$f" ] || EKSIK="$EKSIK $f"; done
if [ -n "$EKSIK" ]; then
  echo "KAYIT KAYNAĞI OKUNAMADI:$EKSIK"
  echo "-> Adım 5'te 'kaynak okunamadı' satırına düş; DRİFT İDDİA ETME."
else
  grep -niE "<alternatif-1>|<alternatif-2>" $KAYNAKLAR
fi
```

Aranan: seçimi **açıkça yapan** bir satır ("X seçildi çünkü…", "Y elendi"). Seçimi **varsayan** satır (D-39'un Fly'ı veri olarak alması) kayıt sayılmaz — tersine, driftin katılaştığının kanıtıdır.

**Adım 5 — Hüküm.**

| Uygulama yüzeyinde | Kayıt | Hüküm |
|---|---|---|
| Alternatiflerin **hepsi** var | — | ❌ bulgu değil — bilinçli çoklu-destek (§6.1) |
| **Hiçbiri** yok | — | ❌ bulgu değil — seçim gerçekten açık; not düş, izle |
| **Tam biri** var | D-NN **var** | ✅ sağlıklı — yalnız metindeki eski "A/B" ifadesini güncelle |
| **Tam biri** var | D-NN **yok** | 🚩 **KARAR DRİFTİ** → §4 katılık + §5 rapor |
| **Tam biri** var | kayıt kaynağı **okunamadı** | ⚠️ **hüküm YOK** — "`internal/` bu makinede yok, kayıt doğrulanamadı" diye raporla. Drift İDDİA ETME (#257 bulgu 9) |

## 4. Katılık — geri almak ne kadar pahalı?

Katılık = seçime bağlı artefaktların **sayısı ve türü**. Sayıyı ölç, türü değerlendir:

```bash
git grep -ilE "<iz>" | wc -l
gh issue list --state all --search "<iz>" --limit 300 --json number | jq length
```

| Derece | Bağlı artefakt | Geri alma maliyeti |
|---|---|---|
| **K0 · sıvı** | yalnız doküman cümlesi | cümleyi düzelt — dakikalar |
| **K1 · şekilleniyor** | + issue başlığı / kabul kriteri | issue'yu yeniden yaz — saatler, board'da görünür |
| **K2 · katı** | + kod/config/CI (`fly.toml`, `Makefile`, workflow) | yazım + test + review — günler |
| **K3 · beton** | + testler, seçimi **varsayan** D-NN'ler, eval veri seti, sprint kanıtı | başka kararları da geri sarar — sprint riski |

**Fly vakası = K3.** Bağlı: `fly.toml` · `Dockerfile:3,75` · `Makefile:71-75` · `docs/sprint3-kontratlar.md:67` · `docs/sprint3-bagimlilik.md` · `eval/datasets/scope-corpus.json` · `ProjectManagement/Sprint3/DailyScrum/daily-scrum-log.md` + açık PR'larda 5 dosya + **D-39/D-43** (Fly'ı varsayan kararlar).

> **K3'te doğru hamle çoğu zaman geri alma değil, kaydı tamamlamaktır.** Drift raporu "seçimi değiştir" demez; "seçim yapıldı, yazılı değil" der. (İstisna: kayıt tamamlanırken kararın kendisi de sorgulanabilir — §2'deki D-46 bunun kanıtı; ama bu **insanın** kararıdır, denetimin önerisi değil.)

## 5. Rapor formatı

Bulgu başına tek blok; oturumda sunulur (issue'ya yorum **yazılmaz**):

```
🚩 KARAR DRİFTİ — <konu>            katılık: K<0-3>
Açık seçim   : <dosya:satır> — "<alıntı>"
Alternatifler: <A> | <B>            (izler: <a-izleri> / <b-izleri>)
Yüzeyde      : A ✓ <n> artefakt · B ✗ 0 artefakt
Kapanış anı  : <tarih> — <artefakt> ("<alıntı>")   ← seçim fiilen burada yapıldı
Kayıt        : yok (arandı: karar_logu D-01..D-NN + vizyon K/A)
Bağlı        : <dosya:satır listesi> + <issue/PR no'ları>
Öneri        : D-NN taslağı ↓ · eski "A/B" ifadesini güncelle: <dosya:satır ×n>
```

Sonunda **D-NN taslağı**, karar logunun kendi satır formatında:

`| **D-NN** | <tarih> | <karar, tek cümle> | <gerekçe: neden A, B niye elendi> | aktif |`

Gerekçe alanı **boş bırakılmaz**. Bilinmiyorsa uydurma — açıkça yaz: *"gerekçe geriye dönük yazıldı; asıl kapanış `<artefakt>`ta oldu"*. Uydurulmuş gerekçe, kaydın yokluğundan daha zararlıdır.

Bulgu yoksa rapor iki cümledir: ne tarandı, kaç işaretçi bakıldı, hepsi neden temiz.

## 6. Yanlış pozitiften kaçınma

Bu denetimin başarısızlık modu kaçırmak değil, **bağırmak**. Aşağıdakiler bulgu **değildir**:

1. **Her iki alternatif de yüzeydeyse** → bilinçli çoklu-destek. Örnek: `Gemini/Ollama` (D-27) · `FAISS/pgvector` ve `Postgres/SQLite` (local↔hosted **mod ayrımı**, tek seçim değil) · `stdio/HTTP-SSE` MCP transport'u (aynı mod ayrımı, `docs/sprint3-kontratlar.md:196`).
2. **Hiçbiri yüzeyde değilse** → seçim gerçekten açık, henüz iş yapılmamış. Örnek: `Slack/Discord` (STRETCH; ne entegrasyon ne issue). Not düş, bir dahakine tekrar bak.
3. **Karşılaştırma/etiket cümleleriyse** → rakip listesi (`Jira/Linear`), tören adları (`Planning/Review`), board sütunları (`Review/Done`), etiket çiftleri (`EXTRACTED/INFERRED`) hiçbir zaman seçim değildir. Kalıba değil, **cümleye** bak.
4. **Gerekçe yazılı ama irtifası düşükse** → bulgu değil, **not**. Örnek: TS client için `Orval/Hey-API` reddi `internal/grup54_backlog.md:521`'de gerekçesiyle yazılı; D-NN değil ama karar kayıp da değil. "Kayıt var, yeri düşük" de; 🚩 basma.
5. **Tek yönlü kapı değilse** → geri dönüş dakikalar sürüyorsa (K0/K1) bulgu üretmek gürültüdür; tek cümlelik uyarı yeter.
6. **Teknik güvenlik/fail-safe dalı, rakip alternatif değildir** → kodda iki alternatifin yanında üçüncü bir dal görürsen önce sor: *bu bir tasarım seçeneği mi, yoksa bir koruma mı?* Örnek: `onboarding/wizard.py` dokümantasyonu "İki mod: Brownfield/Greenfield" der ama kod `mode: str # "greenfield" | "brownfield" | "skipped"` diye **üç** değer döner (`wizard.py:65`); üçüncüsü `.harness/` zaten varsa hiçbir şeye dokunmama fail-safe'idir (`wizard.py:201`, `reason=".harness/ zaten var — dokunulmadı (fail-safe)"`) — rakip bir onboarding stratejisi değil, idempotency guard'ı. Doküman güncellemesi öner (2→3 mod), 🚩 basma.
7. **Emin değilsen yazma.** `docs/review-rehberi.md` §0 ilkesi burada da geçerli: her bulguyu önce **çürütmeye çalış** — *"B'nin izi gerçekten hiç yok mu?"* diye bir tarama daha koş. Bulgunun kanıtı **dosya:satır**dır; "sanırım kayıt yok" bulgu değildir.

## 7. Önleme — asıl iş (denetim ikinci savunma hattı)

Bu hata **issue yazım anında** doğdu: #34/#61 başlıklarına "Fly" yazıldı, sorgulayan kapı yoktu. En ucuz çözüm de orada:

- **Issue yazarken / brifing alırken:** `docs/issue-brifing-rehberi.md` akışına tek soru eklenir — ***"Bu issue, açık bırakılmış bir seçimi kapatıyor mu?"*** Evetse başlamadan önce iki iş çıkar: (a) tek satırlık D-NN, (b) açık seçimi taşıyan cümlelerin güncellenmesi. Brifingin "kapsam bekçiliği" maddesinin kardeşi: o *fazladan işi* yakalar, bu *sessiz kapanışı*.
- **Kabul kriterine bir platform/sağlayıcı/kütüphane adı yazarken:** o ad kriteri **zorunlu** kılar. Yazmadan önce sor: arkasında D-NN var mı? Yoksa önce onu yaz — üç satır, beş dakika.
- **Sprint sınırında:** denetimi tüm repoya koş (`/karar-drifti`). Doğru ritim budur; daha sık = gürültü, daha seyrek = K3.
- **Kayıt üç satırdır.** Karar logunun kendi kuralı zaten şunu diyor: *"Anlamlı bir operasyonel karar verilince buraya bir D-NN satırı ekle."* Bu denetim o kuralın **kaçırdıklarını** sonradan toplar — yerine geçmez.

> **Ürün notu:** Bu, Ensemble için **yeni bir dedektör sınıfı**. scope-drift kapsama, çakışma radarı eşzamanlılığa bakar; hiçbiri "kayıt olmadan katılaşan seçim"i görmez. Ürüne taşıma = backlog/stretch adayı (bkz. ilgili issue).

## 8. İlk denetim — bu repo üzerinde (25 Tem 2026, kısa özet)

Rehberin ilk gerçek çalıştırması, altı konu üzerinden §3 adımlarıyla yapıldı. Sonuç: **1 gerçek drift** (zaten takip issue'su var), **1 aynı sınıf ama henüz ticket'sız aday**, **4 yanlış-pozitif** (§6'ya göre elendi) — yöntemin "bağırmadan bulma" hedefini doğruluyor.

| Konu | Yüzeyde | Kayıt | Hüküm |
|---|---|---|---|
| Judge modeli (`gemini-2.5-flash`) + embedding boyutu (`768`) | `config.py:46-48`, pgvector `vector(768)` (`docs/sprint3-kontratlar.md`), tüm mevcut embedding'ler | yok (D-01..D-46 + K/A tarandı) | 🚩 **DRİFT** — zaten **#244**'e taşındı (bu denetimin ilk gerçek çıktısı) |
| Ollama model ailesi (`llama3.2` + `nomic-embed-text`) | `.env.example:36-37`, `config.py:55-56`, `tests/unit/test_config.py:49-50`, `tests/unit/test_ollama_adapter.py:59,95` (K2) | yok — D-27 yalnız "Ollama capability"yi onaylıyor, hangi model demiyor; `internal/grup54_backlog.md:363` "Model seçim ADR'si" bunu bekliyor ama henüz yazılmadı | 🚩 **#244 ile aynı sınıf**, henüz ayrı ticket yok — backlog'da bekliyor |
| REST/GraphQL (#16) | GitHub ingest'te ikisi de var | `docs/kapsam-sinirlari.md:39`: *"GraphQL sadece GitHub'ı çağırırken (#16). Senin yüzeyin REST+OpenAPI."* — görev ayrımı açıkça yazılı | ✅ sağlıklı, drift değil |
| MCP transport (stdio / HTTP-SSE) | ikisi de var (`docs/sprint3-kontratlar.md:196`) | mod ayrımı (local/hosted), tek seçim değil | ❌ bulgu değil — bilinçli çoklu-destek (§6.1) |
| FAISS/pgvector | ikisi de var (local↔hosted mod) | D-27 kapsamında zaten kayıtlı ayrım | ❌ bulgu değil — bilinçli çoklu-destek (§6.1) |
| Onboarding "iki mod" metni vs. üç değer (`greenfield`/`brownfield`/`skipped`) | `wizard.py:65` üç değer döndürüyor, docstring (`wizard.py:10-11`) yalnız iki mod anlatıyor | — | ❌ bulgu değil — üçüncüsü rakip bir mod değil, fail-safe dalı (§6.6); doküman notu yeterli |

> Kaynak: 25 Tem 2026 Fly/Render vakası → **D-45** (`internal/grup54_karar_logu.md`). Birinci elden doğrulandı: `internal/grup54_vizyon_ve_karar_kaydi.md:99` · #34/#61/#181 · PR #236/#240 · D-46. Rehber değişirse: PR + daily'de duyuru.
