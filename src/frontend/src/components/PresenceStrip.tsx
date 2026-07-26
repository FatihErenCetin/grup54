import type { components } from "../api/schema.d.ts";
import { usePresence } from "../lib/usePresence";
import { ActorChip, hataMesaji } from "./ui";

type PresenceEntry = components["schemas"]["PresenceEntry"];

const SERIT =
  "flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border px-4 py-2.5 text-xs";

/* Presence şeridi — "şu an kim neye dokunuyor".
   Artık CANLI: `GET /presence` (#60) → mock kaldırıldı, "(örnek — canlı S3'te)"
   etiketi de kaldırıldı (etiket dürüstlük içindi; veri gerçek olunca yalan olurdu).

   Üç durumun ÜÇÜ DE görünür — şerit sessizce KAYBOLMAZ:
   - yükleniyor → iskelet (yer tutar, sayfa zıplamaz)
   - hata       → kırmızı şerit + teknik ayrıntı ("kimse yok" ile karıştırılamaz)
   - boş        → "kimse beyan etmemiş" (bu bir hata değil, gerçek bir durum)
   Bayat beyanları backend eler (#60) — istemci ayrıca süzmez. */
export function PresenceStrip() {
  const { data, error, isLoading } = usePresence();
  const entries = data?.entries ?? [];

  if (isLoading) {
    return (
      <div
        aria-busy="true"
        aria-label="Presence yükleniyor"
        className="h-10 animate-pulse rounded-lg bg-muted"
      />
    );
  }

  // != null: openapi-fetch boş-gövdeli non-ok cevapta error="" (falsy!) verebilir —
  // truthiness kontrolü onu yutup sahte "kimse çalışmıyor" basardı (RadarPage'deki
  // aynı bulgu). !data: geçici tek poll hatası eldeki şeridi GİZLEMESİN.
  if (error != null && data === undefined) {
    return (
      <div role="alert" className={`${SERIT} border-severity-high/40 bg-severity-high/10`}>
        <span className="font-medium text-severity-high">
          Presence alınamadı — şu an kimin nerede olduğu bilinmiyor.
        </span>
        <span className="font-mono text-[11px] text-muted-foreground">
          {hataMesaji(error)} · polling sürüyor
        </span>
      </div>
    );
  }

  if (entries.length === 0) {
    return (
      <div className={`${SERIT} border-border bg-card`}>
        <span className="text-muted-foreground">
          Şu an kimse çalışma beyan etmemiş —{" "}
          <span className="font-mono">.harness/active/</span> boş (ya da beyanlar
          bayatladı).
        </span>
      </div>
    );
  }

  return (
    <div className={`${SERIT} border-border bg-card`} aria-label="Şu an çalışanlar">
      <span className="font-medium text-muted-foreground">Şu an</span>
      {entries.map((e) => (
        <PresenceCip key={`${e.actor.handle}-${e.module}`} entry={e} />
      ))}
    </div>
  );
}

function PresenceCip({ entry }: { entry: PresenceEntry }) {
  // Sahte-canlılık yasak (D-34): "3 dk önce" gibi akan bir sayaç uydurmuyoruz;
  // beyanın GERÇEK başlangıç saati tooltip'te, UTC'den yerele çevrilerek durur.
  const detay = [
    entry.task ? `görev: ${entry.task}` : null,
    entry.branch ? `branch: ${entry.branch}` : null,
    entry.actor.responsible ? `sorumlu: ${entry.actor.responsible}` : null,
    `beri: ${new Date(entry.since).toLocaleTimeString("tr-TR")}`,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <span className="inline-flex items-center gap-1.5" title={detay}>
      <ActorChip handle={entry.actor.handle} type={entry.actor.type} />
      <span className="text-muted-foreground">
        → <span className="font-mono">{entry.module}</span>
      </span>
    </span>
  );
}
