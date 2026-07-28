import type { components } from "../api/schema.d.ts";
import {
  ConfidenceMeter,
  EmptyState,
  HataDurumu,
  SonGuncelleme,
  YuklemeIskeleti,
  hataMesaji,
} from "../components/ui";
import { useScope, useScopeVerdicts } from "../lib/useScope";

type ScopeVerdict = components["schemas"]["ScopeVerdict"];

/* Kapsam bekçisi (#33 · tasarım paketi §/scope "Graphite bölümlenmiş liste").
   SOL: `GET /scope/current` — PO'nun dondurduğu sprint kapsamı (CANLI, ~2KB).
   SAĞ: `GET /scope/verdicts` — açık ref'lerin kararları; uç 200 döner ama
   liste bugün BOŞ (kararlar PR ingest'iyle dolar) → "yakında"yı uydurmak
   yerine ucun GERÇEK boş cevabını çiziyoruz; ingest başlayınca panel
   kendiliğinden dolar, silinecek placeholder kod yok.

   Bilinçli tasarım sapması: pakette sağ sütun "ana alan", sol panel dar.
   Bugün gerçek içerik solda (goal 614 karakter + 6+6 madde), sağ taraf boş →
   ağırlığı sola verdim. Veri gelince oran tersine döner (tek satır grid).

   Gate'li (eksik DEĞİL): `GET /scope/check?ref=` nokta-sorgusu hook'lanmadı
   (liste ucu zaten hepsini taşıyor) · kapsam düzenleme/dondurma yazma ucu
   MVP'de yok (.harness/scope PO'nun git'teki dosyası — D-34 "iş yapmayan
   buton basmıyoruz"). */
export default function ScopePage() {
  const { data, error, isLoading, isFetching, dataUpdatedAt } = useScope();

  if (isLoading) {
    return <YuklemeIskeleti label="Kapsam yükleniyor" satir={4} />;
  }

  // != null: openapi-fetch boş-gövdeli non-ok cevapta error="" (falsy!) verebilir —
  // truthiness kontrolü onu yutup sahte "kapsam yok" basardı (RadarPage'deki bulgu).
  // data === undefined: geçici tek poll hatası eldeki kapsamı GİZLEMESİN.
  // Açıklama özelleştirildi: burada en olası hata bağlantı değil, 503
  // `scope_unavailable` (scope belgesi frozen değil) — genel metin yanıltırdı.
  if (error != null && data === undefined) {
    return (
      <HataDurumu
        baslik="Kapsam belgesine ulaşılamıyor"
        aciklama="Ya backend cevap vermedi (bağlantı · VITE_API_BASE_URL) ya da .harness/scope/ belgesi henüz PO tarafından dondurulmadı (503 scope_unavailable). Polling sürüyor; düzelince kendiliğinden gelir."
        hata={error}
      />
    );
  }

  const goal = data?.goal?.trim() ?? "";
  const inScope = data?.in_scope ?? [];
  const nonGoals = data?.non_goals ?? [];

  // Boş ≠ hata: kapsam belgesi var ama içi boşsa dürüstçe söyle (backend bunu
  // normalde 503'e çevirir; yine de sessiz boş sayfa basmıyoruz).
  if (goal === "" && inScope.length === 0 && nonGoals.length === 0) {
    return (
      <EmptyState
        title="Dondurulmuş kapsam boş"
        description="Uç cevap verdi ama kapsam belgesinde amaç, kapsam içi ve kapsam dışı maddelerin üçü de boş. Kapsam PO tarafından .harness/scope/sprint-N.md içinde yazılır ve dondurulur."
        eta="Kaynak: .harness/scope/ · GET /scope/current"
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-base font-semibold">Kapsam Bekçisi</h1>
        <SonGuncelleme dataUpdatedAt={dataUpdatedAt} isFetching={isFetching} />
      </div>

      {data && <KunyeSeridi scope={data} />}

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <section
          aria-label="Dondurulmuş sprint kapsamı"
          className="space-y-4 rounded-lg border border-border bg-card p-4"
        >
          {goal !== "" && <Amac goal={goal} />}

          <KapsamBolumu
            baslik="Kapsam içi"
            aciklama="Bu sprintte yapılacağı dondurulan maddeler."
            isaret="✓"
            isaretSinifi="text-status-done"
            maddeler={inScope}
            bosMetin="Kapsam içi madde yok — kapsam belgesi en az bir madde taşımalı."
          />

          <KapsamBolumu
            baslik="Kapsam dışı"
            aciklama="Bilinçli olarak yapılmayacaklar; drift kararı bunlara göre verilir."
            isaret="⊘"
            isaretSinifi="text-muted-foreground"
            maddeler={nonGoals}
            bosMetin="Kapsam dışı madde tanımlanmamış — PO bu sprint için açık bir “yapmayacağız” listesi yazmamış."
            soluk
          />
        </section>

        <KararlarPaneli />
      </div>
    </div>
  );
}

/* ── Sol sütun ────────────────────────────────────────────────────────── */

/** Kapsamın kimliği: hangi sürüm, hangi commit, ne zaman donduruldu.
    Sahte-canlılık yasak (D-34): frozen_at GERÇEK zaman damgası, yerele çevrilir. */
function KunyeSeridi({ scope }: { scope: components["schemas"]["ScopeCurrent"] }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-border bg-card px-4 py-2.5 text-xs">
      <span className="inline-flex items-center gap-1.5 rounded bg-status-done/15 px-1.5 py-0.5 font-medium text-status-done">
        <span aria-hidden>✓</span>
        Dondurulmuş
      </span>
      <Kunye etiket="sürüm" deger={scope.version} />
      <Kunye etiket="ref" deger={scope.ref} />
      <Kunye
        etiket="commit"
        deger={scope.commit_sha.slice(0, 7)}
        baslik={scope.commit_sha}
      />
      <span className="text-muted-foreground">
        Donduruldu: <span className="tabular-nums">{zaman(scope.frozen_at)}</span>
      </span>
    </div>
  );
}

function Kunye({
  etiket,
  deger,
  baslik,
}: {
  etiket: string;
  deger: string;
  baslik?: string;
}) {
  return (
    <span className="text-muted-foreground">
      {etiket}:{" "}
      <span className="font-mono text-foreground" title={baslik}>
        {deger}
      </span>
    </span>
  );
}

/** Amaç metni = scope belgesinin gövdesi: çok paragraflı düz yazı.
    Tek blok basmak okunmaz kılıyordu → paragrafa bölünür, ölçü prose
    genişliğiyle sınırlanır. İlk satır kaynakta köşeli parantezli bir
    künye ise (bugün öyle) üstbilgi gibi soluk basılır; değilse normal
    paragraf olarak akar (biçim değişirse sessizce bozulmaz). */
function Amac({ goal }: { goal: string }) {
  const paragraflar = goal.split(/\n{2,}/).map((p) => p.trim()).filter(Boolean);
  const ilk = paragraflar[0] ?? "";
  const kunyeVar = ilk.startsWith("[") && ilk.endsWith("]");
  const govde = kunyeVar ? paragraflar.slice(1) : paragraflar;

  return (
    <section className="space-y-2.5">
      <BolumBasligi baslik="Amaç" />
      {kunyeVar && (
        <p className="font-mono text-[11px] leading-relaxed text-muted-foreground">
          {ilk.slice(1, -1)}
        </p>
      )}
      <div className="max-w-[68ch] space-y-3">
        {govde.map((p, i) => (
          <p key={i} className="text-sm leading-relaxed">
            <Metin>{p}</Metin>
          </p>
        ))}
      </div>
    </section>
  );
}

function KapsamBolumu({
  baslik,
  aciklama,
  isaret,
  isaretSinifi,
  maddeler,
  bosMetin,
  soluk = false,
}: {
  baslik: string;
  aciklama: string;
  isaret: string;
  isaretSinifi: string;
  maddeler: string[];
  bosMetin: string;
  /** Kapsam dışı bloğu: alarm rengiyle değil, zeminle ayrışır (yanlış aciliyet üretmesin) */
  soluk?: boolean;
}) {
  return (
    <section className="space-y-2.5">
      <BolumBasligi baslik={baslik} sayi={maddeler.length} />
      <p className="text-xs text-muted-foreground">{aciklama}</p>
      {maddeler.length === 0 ? (
        <p className="text-sm text-muted-foreground">{bosMetin}</p>
      ) : (
        <ol className="space-y-2">
          {maddeler.map((madde, i) => (
            <li
              key={`${i}-${madde.slice(0, 24)}`}
              className={`flex gap-3 rounded-lg border border-border px-4 py-3 ${
                soluk ? "bg-muted/30" : "bg-background"
              }`}
            >
              {/* İşaret + sayı + TR bölüm başlığı birlikte: renk tek başına
                  anlam taşımaz (D-34) */}
              <span className="flex shrink-0 items-baseline gap-1.5">
                <span aria-hidden className={`text-xs ${isaretSinifi}`}>
                  {isaret}
                </span>
                <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
                  {i + 1}
                </span>
              </span>
              <span className="min-w-0 text-sm leading-relaxed">
                <Metin>{madde}</Metin>
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

/* ── Sağ sütun: kapsam kararları ──────────────────────────────────────── */

const KARAR_STILI: Record<
  ScopeVerdict["verdict"],
  { etiket: string; ikon: string; cls: string }
> = {
  // Renk + ikon + TR etiket birlikte (D-34)
  in_scope: { etiket: "kapsam içi", ikon: "✓", cls: "bg-status-done/15 text-status-done" },
  drift: { etiket: "kayma", ikon: "◆", cls: "bg-severity-med/15 text-severity-med" },
  non_goal_violation: {
    etiket: "kapsam dışı ihlal",
    ikon: "▲",
    cls: "bg-severity-high/15 text-severity-high",
  },
};

const BOLUM_ADI: Record<"goal" | "in_scope" | "non_goals", string> = {
  goal: "amaç",
  in_scope: "kapsam içi",
  non_goals: "kapsam dışı",
};

/** Açık ref'lerin kapsam kararları. Üç durumun ÜÇÜ DE çizilir; panel sessizce
    kaybolmaz. Kendi verisini kendi çeker (PresenceStrip kalıbı) → sol sütun
    sağın hatasından etkilenmez. */
function KararlarPaneli() {
  const { data, error, isLoading, isFetching, dataUpdatedAt } = useScopeVerdicts();

  const govde = () => {
    if (isLoading) {
      return <YuklemeIskeleti label="Kapsam kararları yükleniyor" satir={2} />;
    }

    // != null + data === undefined: aynı fail-open kuralı (boş gövdeli hata "" gelir)
    if (error != null && data === undefined) {
      return (
        <div
          role="alert"
          className="space-y-1 rounded-lg border border-severity-high/40 bg-severity-high/10 px-4 py-3 text-xs"
        >
          <p className="font-medium text-severity-high">
            Kapsam kararları alınamadı — PR'ların kapsam içinde olup olmadığı bilinmiyor.
          </p>
          <p className="font-mono text-[11px] text-muted-foreground">
            {hataMesaji(error)} · polling sürüyor
          </p>
        </div>
      );
    }

    const verdicts = data?.verdicts ?? [];

    if (verdicts.length === 0) {
      // Boş ≠ hata: uç 200 döndü, henüz karar üretilmemiş. "Yakında" uydurmak
      // yerine ucun gerçek cevabını (0/0/0, judged_at: null) gösteriyoruz.
      return (
        <div className="space-y-2 rounded-lg border border-border bg-background px-4 py-3">
          <p className="text-sm">Henüz kapsam kararı yok.</p>
          <p className="text-xs leading-relaxed text-muted-foreground">
            Açık PR'lar ingest edildikçe her biri soldaki dondurulmuş kapsama karşı
            yargılanacak; karar rozeti, güven değeri ve kapsam belgesinden kanıt
            alıntısı bu listede görünecek.
          </p>
          <p className="font-mono text-[10px] text-muted-foreground">
            GET /scope/verdicts → 200 · judged_at: yok
          </p>
        </div>
      );
    }

    return (
      <ul className="space-y-2">
        {verdicts.map((v) => (
          <KararSatiri key={v.ref} verdict={v} />
        ))}
      </ul>
    );
  };

  return (
    <section
      aria-label="Kapsam kararları"
      className="space-y-3 rounded-lg border border-border bg-card p-4"
    >
      <div className="flex items-center justify-between gap-3">
        <BolumBasligi baslik="PR kapsam kararları" />
        <SonGuncelleme dataUpdatedAt={dataUpdatedAt} isFetching={isFetching} />
      </div>

      {data && (
        <div className="flex flex-wrap gap-1.5">
          {(["in_scope", "drift", "non_goal_violation"] as const).map((k) => {
            const s = KARAR_STILI[k];
            return (
              <span
                key={k}
                className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs ${s.cls}`}
              >
                <span aria-hidden>{s.ikon}</span>
                {s.etiket}
                <span className="font-medium tabular-nums">{data.counts[k]}</span>
              </span>
            );
          })}
        </div>
      )}

      {govde()}
    </section>
  );
}

function KararSatiri({ verdict }: { verdict: ScopeVerdict }) {
  const s = KARAR_STILI[verdict.verdict];
  // evidence bir UNION: düz string ya da ScopeItemRef — `.quote`'a kör erişmiyoruz.
  const ev = verdict.evidence;
  const alinti = typeof ev === "string" ? ev : ev.quote;
  const bolum = typeof ev === "string" ? null : (ev.section ?? null);
  const maddeId = typeof ev === "string" ? null : (ev.item_id ?? null);
  const satir = typeof ev === "string" ? null : (ev.line ?? null);

  const kanitMeta = [
    bolum ? BOLUM_ADI[bolum] : null,
    maddeId,
    satir !== null ? `satır ${satir}` : null,
  ].filter(Boolean);

  return (
    <li className="space-y-2 rounded-lg border border-border bg-background px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium ${s.cls}`}
        >
          <span aria-hidden>{s.ikon}</span>
          {s.etiket}
        </span>
        <span className="min-w-0 flex-1 truncate font-mono text-xs" title={verdict.ref}>
          {verdict.ref}
        </span>
        <ConfidenceMeter value={verdict.confidence} />
      </div>

      {alinti.trim() !== "" && (
        <blockquote className="border-l-2 border-border pl-3 text-xs leading-relaxed text-muted-foreground">
          “{alinti}”
          {kanitMeta.length > 0 && (
            <span className="mt-1 block font-mono text-[10px]">
              {kanitMeta.join(" · ")}
            </span>
          )}
        </blockquote>
      )}

      <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
        {verdict.match_none && (
          <span>⊘ eşleşen kapsam maddesi yok</span>
        )}
        {verdict.signals && verdict.signals.files.length > 0 && (
          <span
            className="truncate font-mono"
            title={verdict.signals.files.join(", ")}
          >
            {verdict.signals.files.length} dosya
          </span>
        )}
        {verdict.judged_at && (
          <span className="tabular-nums">Karar: {zaman(verdict.judged_at)}</span>
        )}
      </div>
    </li>
  );
}

/* ── Ortak küçük parçalar ─────────────────────────────────────────────── */

function BolumBasligi({ baslik, sayi }: { baslik: string; sayi?: number }) {
  // ALL-CAPS yok (TR İ/ı tuzağı, D-34) — hiyerarşi punto + ağırlık + renkle
  return (
    <h2 className="flex items-baseline gap-2 text-[11px] font-semibold tracking-wide text-muted-foreground">
      {baslik}
      {sayi !== undefined && (
        <span className="font-normal tabular-nums">{sayi} madde</span>
      )}
    </h2>
  );
}

/** Kapsam metnindeki referansları (issue no · karar kodu · dosya yolu) mono'ya
    çevirir — house kuralı: T-id, dosya yolu, modül adı mono. Uzun maddelerde
    göz bunlara tutunuyor. Eşleşme yoksa metin aynen akar. */
const REF_DESENI =
  /((?:docs|src|tests|eval|\.harness|\.github)\/[^\s,;)]+|#\d+|\b[A-Z]-\d+\b)/;

function Metin({ children }: { children: string }) {
  // split + yakalama grubu: tek çift indeksler düz metin, tekler referans
  const parcalar = children.split(REF_DESENI);
  return (
    <>
      {parcalar.map((p, i) =>
        i % 2 === 1 ? (
          <span key={i} className="font-mono text-[0.95em]">
            {p}
          </span>
        ) : (
          p
        ),
      )}
    </>
  );
}

/** ISO zaman damgasını yerel saate çevirir; bozuk değer sessizce "Invalid Date"
    olmaz, ham metin basılır (uydurmak yerine dürüst ham veri). */
function zaman(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("tr-TR");
}
