import { useMemo } from "react";
import type { ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import type { components } from "../api/schema.d.ts";
import { moduleOf } from "../components/FeedItem";
import {
  ActorChip,
  ConfidenceMeter,
  EmptyState,
  HataDurumu,
  SeverityBadge,
  SonGuncelleme,
  YuklemeIskeleti,
  aktorTipiSezgisi,
} from "../components/ui";
import { useBoard } from "../lib/useBoard";
import { useEvents } from "../lib/useEvents";
import { usePresence } from "../lib/usePresence";
import { useRadar } from "../lib/useRadar";
import { parseUtc } from "./ActivityPage";

type NormalizedEvent = components["schemas"]["NormalizedEvent"];
type BoardCard = components["schemas"]["BoardCard"];
type Detection = components["schemas"]["Detection"];
type PresenceEntry = components["schemas"]["PresenceEntry"];

/* Aktör hub sayfası (#129) — "profil" ihtiyacının D-23-uyumlu çözümü
   (login/DB YOK, frontend-only, SIFIR yeni endpoint).

   Dört mevcut uçtan BESLENİR, hepsi zaten başka sayfaların kullandığı hook'lar
   — burada yalnızca `handle`'a göre CLIENT-SIDE süzülür:
     /events   -> bu aktörün olayları  (useEvents)
     /radar    -> bu aktörün geçtiği tespitler (useRadar)
     /board    -> bu aktöre atanmış kartlar (useBoard)
     /presence -> şu an neye dokunuyor + gerçek ActorRef.type/responsible (usePresence)

   İnsan/ajan tipi: presence'ta bu handle AKTİF beyanlıysa ActorRef.type/
   responsible GERÇEKTİR (Ek B1); değilse `aktorTipiSezgisi` ile handle
   sonekinden SEZİLİR (tahmin ≠ veri — ActorChip'in kendi ilkesiyle aynı).
   Bu yüzden "ajan" rozeti/pair-zinciri aktif değilken de görünür ama dürüstçe
   "sezgiyle" işaretlenir; uydurma responsible YAZILMAZ ("beyan yok" yazılır).

   Gate'li (bilinçli, eksik DEĞİL — görev kapsamı #129 metninde net):
   - `/board?assignee=` · `/radar?actor=` deep-link'leri buradan ÜRETİLİR;
     hedef sayfaların bu query-param'ı OKUYUP ön-süzmesi ayrı bir iş (Board/
     Radar/Graph "minimum değiştir, yalnız link ekle" kapsamıyla sınırlı) —
     bugün yalnız o sayfaya GÖTÜRÜR, otomatik filtrelemez.
   - `/graph` linki filtresiz: TouchGraph bu sayfanın 3 bloğuna dahil değil
     (görev talimatı 4 uçla sınırlı: events/radar/board/presence). */

const AJAN_YAPAMAZ = [
  "Board kartı taşıyamaz — durumu yalnız ingest yazar (CRUD yasağı, D-23)",
  "Scope'u (in_scope/non_goals) değiştiremez — .harness/scope insan dondurur",
  "Bir kararı (D-NN) tek başına COMMIT'leyemez — taslak üretir, insan onaylar",
  ".harness/active dışına kendiliğinden YAZAMAZ — yazma ucu MVP'de yok (S3-stretch)",
];

const DURUM_ETIKET: Record<BoardCard["status"], { etiket: string; ikon: string; cip: string }> = {
  backlog: { etiket: "Backlog", ikon: "○", cip: "bg-status-backlog/15 text-status-backlog" },
  todo: { etiket: "Yapılacak", ikon: "◔", cip: "bg-status-todo/15 text-status-todo" },
  in_progress: {
    etiket: "Devam ediyor",
    ikon: "◑",
    cip: "bg-status-in-progress/15 text-status-in-progress",
  },
  in_review: { etiket: "İncelemede", ikon: "◕", cip: "bg-status-in-review/15 text-status-in-review" },
  done: { etiket: "Bitti", ikon: "●", cip: "bg-status-done/15 text-status-done" },
};

const TUR_ETIKET: Record<string, { etiket: string; ikon: string; ton: string }> = {
  commit: { etiket: "commit", ikon: "◆", ton: "bg-primary/15 text-primary" },
  pr: { etiket: "PR", ikon: "⇢", ton: "bg-status-in-review/15 text-status-in-review" },
  issue: { etiket: "issue", ikon: "◈", ton: "bg-status-todo/15 text-status-todo" },
};

/** Bozuk ISO'da "Invalid Date" basma — Activity/Graph ile aynı guard. */
function zamanMetni(iso: string): string {
  const d = parseUtc(iso);
  if (Number.isNaN(d.getTime())) return "tarih okunamadı";
  return d.toLocaleString("tr-TR", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Göreli yaş DAİMA gerçek saatin YANINDA ikincil bilgi (sahte-canlılık yasak, D-34). */
function yasMetniDakika(dakika: number | null): string {
  if (dakika === null) return "yaş okunamadı";
  if (dakika < 1) return "az önce";
  if (dakika < 60) return `${Math.floor(dakika)} dk önce`;
  return `${Math.floor(dakika / 60)} sa önce`;
}

export default function ActorPage() {
  const { handle } = useParams<{ handle: string }>();
  const events = useEvents();
  const board = useBoard();
  const radar = useRadar();
  const presence = usePresence();

  // Erken-return'lerden ÖNCE (hook kuralı) — `handle` boşsa aşağıdaki hook'lar
  // yine de çağrılmış olur, süzme sonucu boş kalır.
  const guvenliHandle = handle ?? "";

  const kendiOlaylari = useMemo<NormalizedEvent[]>(() => {
    const liste = (events.data?.events ?? []).filter((e) => e.actor === guvenliHandle);
    return [...liste].sort((a, b) => parseUtc(b.ts).getTime() - parseUtc(a.ts).getTime());
  }, [events.data, guvenliHandle]);

  const kendiKartlari = useMemo<BoardCard[]>(
    () => (board.data?.cards ?? []).filter((c) => c.assignee === guvenliHandle),
    [board.data, guvenliHandle],
  );

  const kendiTespitleri = useMemo<Detection[]>(
    () => (radar.data?.detections ?? []).filter((d) => d.actors.includes(guvenliHandle)),
    [radar.data, guvenliHandle],
  );

  const presenceGirdisi = useMemo<PresenceEntry | null>(
    () => presence.data?.entries.find((e) => e.actor.handle === guvenliHandle) ?? null,
    [presence.data, guvenliHandle],
  );

  const tip = presenceGirdisi?.actor.type ?? aktorTipiSezgisi(guvenliHandle);
  const isAgent = tip === "agent";

  // Dört uç HEPSİ başarıyla döndüyse VE süzülen sonuç dört yerde de boşsa
  // "gerçekten boş" diyoruz — herhangi biri yükleniyor/hatalıysa (data===
  // undefined) SESSİZCE "boş" denmez, o blok kendi durumunu ayrı gösterir.
  const dortuDeDondu =
    events.data !== undefined &&
    board.data !== undefined &&
    radar.data !== undefined &&
    presence.data !== undefined;
  const hicVeriYok =
    dortuDeDondu &&
    presenceGirdisi === null &&
    kendiOlaylari.length === 0 &&
    kendiKartlari.length === 0 &&
    kendiTespitleri.length === 0;

  if (!handle) {
    return <HataDurumu baslik="Aktör belirtilmemiş" aciklama="/actors/:handle rotası bir handle bekliyor." />;
  }

  const enSonGuncelleme = Math.max(
    events.dataUpdatedAt,
    board.dataUpdatedAt,
    radar.dataUpdatedAt,
    presence.dataUpdatedAt,
  );
  const herhangiFetchEdiyor =
    events.isFetching || board.isFetching || radar.isFetching || presence.isFetching;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-base font-semibold">
          Aktör <span className="font-mono">{handle}</span>
        </h1>
        <SonGuncelleme dataUpdatedAt={enSonGuncelleme} isFetching={herhangiFetchEdiyor} />
      </div>

      <KimlikBlogu
        handle={handle}
        isAgent={isAgent}
        presenceGirdisi={presenceGirdisi}
        presence={presence}
      />

      {hicVeriYok &&
        (isAgent ? <AjanBosDurum handle={handle} /> : <InsanBosDurum handle={handle} />)}

      <OlaylarBlok handle={handle} olaylar={kendiOlaylari} durum={events} />
      <KartlarBlok handle={handle} kartlar={kendiKartlari} durum={board} />
      <TespitlerBlok handle={handle} tespitler={kendiTespitleri} durum={radar} />
    </div>
  );
}

/* ── Kimlik bloğu: insan/ajan varyantı + pair zinciri + presence şeridi ──── */

function KimlikBlogu({
  handle,
  isAgent,
  presenceGirdisi,
  presence,
}: {
  handle: string;
  isAgent: boolean;
  presenceGirdisi: PresenceEntry | null;
  presence: ReturnType<typeof usePresence>;
}) {
  const initials = handle.slice(0, 2).toUpperCase();
  const sezgiyle = presenceGirdisi === null;

  // Beyan yaşı + bayatlık soluklaşması (#129 kabul kriteri): backend zaten
  // bayat beyanları eler (usePresence yorumu) — burada gördüğümüz her şey
  // "taze" ama presence penceresi içinde göreceli tazelik yine de anlamlı.
  let yasDakika: number | null = null;
  if (presenceGirdisi) {
    const t = parseUtc(presenceGirdisi.since).getTime();
    yasDakika = Number.isNaN(t) ? null : Math.max(0, (presence.dataUpdatedAt - t) / 60_000);
  }
  const soluklukSinifi =
    yasDakika === null ? "" : yasDakika < 15 ? "" : yasDakika < 45 ? "opacity-80" : "opacity-60";

  let presenceGovde: ReactNode;
  if (presence.isLoading) {
    presenceGovde = (
      <div className="h-8 animate-pulse rounded bg-muted" aria-busy="true" aria-label="Presence yükleniyor" />
    );
  } else if (presence.error != null && presence.data === undefined) {
    // != null: openapi-fetch boş-gövdeli non-ok cevapta error="" (falsy!) verebilir (ev bulgusu).
    presenceGovde = <HataDurumu baslik="Presence'a ulaşılamıyor" hata={presence.error} />;
  } else if (presenceGirdisi) {
    presenceGovde = (
      <div className={`flex flex-wrap items-center gap-x-4 gap-y-1 text-xs ${soluklukSinifi}`}>
        <span className="font-medium text-primary">
          <span aria-hidden>◎ </span>Şu an aktif
        </span>
        <span className="text-muted-foreground">
          modül: <span className="font-mono text-foreground">{presenceGirdisi.module}</span>
        </span>
        {presenceGirdisi.task && (
          <span className="text-muted-foreground">
            görev: <span className="font-mono text-foreground">{presenceGirdisi.task}</span>
          </span>
        )}
        {presenceGirdisi.branch && (
          <span className="text-muted-foreground">
            branch: <span className="font-mono text-foreground">{presenceGirdisi.branch}</span>
          </span>
        )}
        <span
          className="text-muted-foreground"
          title={parseUtc(presenceGirdisi.since).toLocaleString("tr-TR")}
        >
          beyan yaşı: {yasMetniDakika(yasDakika)}
        </span>
      </div>
    );
  } else {
    presenceGovde = (
      <p className="text-xs text-muted-foreground">
        Şu an aktif bir beyan yok — <span className="font-mono">.harness/active/</span>'ta bu handle
        görünmüyor (hiç beyan edilmemiş ya da bayatladığı için backend elemiş olabilir).
      </p>
    );
  }

  return (
    <div className="space-y-3 rounded-lg border border-border bg-card p-4">
      <div className="flex flex-wrap items-start gap-4">
        <span
          aria-hidden
          className={`inline-flex size-12 shrink-0 items-center justify-center bg-muted text-base font-semibold ${
            isAgent ? "rounded-md" : "rounded-full"
          }`}
        >
          {initials}
        </span>
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-mono text-base font-semibold">{handle}</h2>
            {isAgent && (
              <span className="rounded bg-status-in-review/15 px-1.5 py-0.5 text-xs font-medium text-status-in-review">
                <span aria-hidden>▪ </span>AI ajanı
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground">
            {isAgent ? "ajan" : "insan"}
          </p>
          {/* Sezgi notu yalnız AJAN tarafında: "insan" tarafı handle'da agent
              soneki YOKLUĞUna dayanır ve pratikte neredeyse her zaman doğrudur
              — her aktif-olmayan insanda bu notu tekrarlamak gürültü olurdu.
              Ajan tarafında ise sorumlu/pair bilgisi GERÇEKTEN belirsiz olabilir. */}
          {isAgent && sezgiyle && (
            <p className="text-xs text-muted-foreground">
              handle sonekinden sezildi — presence'ta şu an aktif değil, kesin ActorRef yok.
            </p>
          )}
          {isAgent && (
            // Pair zinciri: kabul kriteri "sorumluluk zinciri boşken de görünür" —
            // aktivite/presence sıfır olsa bile bu satır HER ZAMAN çizilir;
            // responsible bilinmiyorsa uydurulmaz, dürüstçe "beyan yok" yazılır.
            <p className="font-mono text-xs text-muted-foreground">
              eller: {handle} · sorumlu:{" "}
              {presenceGirdisi?.actor.responsible ?? "beyan yok (şu an aktif değil)"}
            </p>
          )}
        </div>
      </div>

      {presenceGovde}

      {isAgent && (
        <div className="space-y-1.5 border-t border-border pt-3">
          <h3 className="text-[11px] font-semibold tracking-wide text-muted-foreground">
            Bu ajan yapamaz
          </h3>
          <ul className="space-y-1 text-xs text-muted-foreground">
            {AJAN_YAPAMAZ.map((satir) => (
              <li key={satir} className="flex gap-1.5">
                <span aria-hidden>✕</span>
                <span>{satir}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/* ── Boş durumlar: insan = 3-adım davet · ajan = kısa açıklama (pair zinciri
   yukarıda zaten görünür durumda, burada tekrar edilmez) ──────────────────── */

function InsanBosDurum({ handle }: { handle: string }) {
  return (
    <EmptyState
      title="Henüz aktivite yok"
      description={`${handle} için olay/kart/tespit/presence kaydı yok — bu bir hata değil, sıfır endpoint'li bir süzme (dört mevcut uç da başarıyla döndü, hepsi boş). Üç adımda görünür olursun:`}
      items={[
        `1) .harness/active/${handle}.md dosyanı oluştur (modül · T-<id> · niyet)`,
        "2) T-<id>-kısa-açıklama dalında commit at",
        "3) PR aç — Board/Radar/Activity kendiliğinden dolar, bu sayfa da onlardan besleniyor",
      ]}
    />
  );
}

function AjanBosDurum({ handle }: { handle: string }) {
  return (
    <EmptyState
      title="Bu ajan için henüz aktivite yok"
      description={`Sorumluluk zinciri yukarıda görünür durumda; ${handle} aktivite üretince (commit/PR/kart/tespit) burada listelenecek. Bir ajan kendiliğinden görünür olmaz — sorumlu insan onu .harness/active/<handle>-<araç>.md ile beyan eder.`}
    />
  );
}

/* ── 3 aktivite bloğu: Olaylar / Board kartları / Tespitler — hepsi mevcut
   kontrat verisinin client-side süzmesi (#129 kabul kriteri, YENİ ENDPOINT YOK). ── */

function OlaylarBlok({
  handle,
  olaylar,
  durum,
}: {
  handle: string;
  olaylar: NormalizedEvent[];
  durum: ReturnType<typeof useEvents>;
}) {
  return (
    <section className="space-y-2 rounded-lg border border-border bg-card p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-medium">
          Olaylar <span className="tabular-nums text-muted-foreground">({olaylar.length})</span>
        </h2>
        <Link to="/activity" className="text-xs text-muted-foreground hover:text-foreground hover:underline">
          Activity'de gör →
        </Link>
      </div>
      {durum.isLoading ? (
        <YuklemeIskeleti label={`${handle} olayları yükleniyor`} satir={2} />
      ) : durum.error != null && durum.data === undefined ? (
        <HataDurumu baslik="Bu aktörün olaylarına ulaşılamıyor" hata={durum.error} />
      ) : olaylar.length === 0 ? (
        <p className="text-xs text-muted-foreground">Bu aktörün henüz izlenen bir olayı yok.</p>
      ) : (
        <ul aria-label={`${handle} olayları`} className="divide-y divide-border">
          {olaylar.map((e) => {
            const tur = TUR_ETIKET[e.type] ?? { etiket: e.type, ikon: "•", ton: "bg-muted text-muted-foreground" };
            return (
              <li key={e.id} className="flex items-center gap-2 py-2 text-sm">
                <span className={`shrink-0 rounded px-1.5 py-0.5 text-[11px] ${tur.ton}`}>
                  <span aria-hidden>{tur.ikon} </span>
                  {tur.etiket}
                </span>
                <span className="min-w-0 flex-1 truncate font-mono text-xs text-muted-foreground">
                  {e.branch ?? "dalsız"}
                </span>
                <span className="shrink-0 text-[11px] tabular-nums text-muted-foreground">
                  {zamanMetni(e.ts)}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function KartlarBlok({
  handle,
  kartlar,
  durum,
}: {
  handle: string;
  kartlar: BoardCard[];
  durum: ReturnType<typeof useBoard>;
}) {
  return (
    <section className="space-y-2 rounded-lg border border-border bg-card p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-medium">
          Board kartları <span className="tabular-nums text-muted-foreground">({kartlar.length})</span>
        </h2>
        <Link
          to={`/board?assignee=${encodeURIComponent(handle)}`}
          className="text-xs text-muted-foreground hover:text-foreground hover:underline"
        >
          Board'da gör →
        </Link>
      </div>
      {durum.isLoading ? (
        <YuklemeIskeleti label={`${handle} kartları yükleniyor`} satir={2} />
      ) : durum.error != null && durum.data === undefined ? (
        <HataDurumu baslik="Bu aktöre atanmış kartlara ulaşılamıyor" hata={durum.error} />
      ) : kartlar.length === 0 ? (
        <p className="text-xs text-muted-foreground">Bu aktöre atanmış kart yok.</p>
      ) : (
        <ul className="space-y-2">
          {kartlar.map((k) => {
            const d = DURUM_ETIKET[k.status];
            return (
              <li key={k.task_id} className="flex items-center gap-2 rounded border border-border px-3 py-2">
                <span className="shrink-0 font-mono text-xs text-muted-foreground">{k.task_id}</span>
                <span className="min-w-0 flex-1 truncate text-sm" title={k.title}>
                  {k.title}
                </span>
                {d ? (
                  <span className={`shrink-0 rounded px-1.5 py-0.5 text-xs font-medium ${d.cip}`}>
                    <span aria-hidden>{d.ikon} </span>
                    {d.etiket}
                  </span>
                ) : (
                  <span className="shrink-0 font-mono text-[10px] text-muted-foreground">{k.status}</span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function TespitlerBlok({
  handle,
  tespitler,
  durum,
}: {
  handle: string;
  tespitler: Detection[];
  durum: ReturnType<typeof useRadar>;
}) {
  return (
    <section className="space-y-2 rounded-lg border border-border bg-card p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-medium">
          Tespitler <span className="tabular-nums text-muted-foreground">({tespitler.length})</span>
        </h2>
        <Link
          to={`/radar?actor=${encodeURIComponent(handle)}`}
          className="text-xs text-muted-foreground hover:text-foreground hover:underline"
        >
          Radar'da gör →
        </Link>
      </div>
      {durum.isLoading ? (
        <YuklemeIskeleti label={`${handle} tespitleri yükleniyor`} satir={2} />
      ) : durum.error != null && durum.data === undefined ? (
        <HataDurumu baslik="Bu aktörün geçtiği tespitlere ulaşılamıyor" hata={durum.error} />
      ) : tespitler.length === 0 ? (
        <p className="text-xs text-muted-foreground">Bu aktörün geçtiği bir çakışma tespiti yok.</p>
      ) : (
        <ul className="space-y-2">
          {tespitler.map((d) => {
            const digerAktorler = d.actors.filter((a) => a !== handle);
            return (
              <li key={d.id} className="space-y-1.5 rounded border border-border px-3 py-2">
                <div className="flex items-center gap-3">
                  <SeverityBadge level={d.severity} />
                  <span className="min-w-0 flex-1 truncate text-sm" title={d.rationale}>
                    {d.rationale}
                  </span>
                  <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground">
                    {moduleOf(d.files)}
                  </span>
                  <ConfidenceMeter value={d.confidence} />
                </div>
                {digerAktorler.length > 0 && (
                  <div className="flex flex-wrap items-center gap-2 pl-1">
                    <span className="text-[11px] text-muted-foreground">diğer aktör(ler):</span>
                    {digerAktorler.map((a) => (
                      <ActorChip key={a} handle={a} linkli />
                    ))}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
