import { mockPresence } from "../mocks/presence";
import { ActorChip } from "./ui";

/* Presence şeridi (#21) — "şu an kim neye dokunuyor".
   Ek B1: GET /presence S3 kontratı; o güne dek veri HER ZAMAN örnektir ve
   şerit kendi "(örnek)" etiketini mock bayrağından BAĞIMSIZ taşır — global
   ÖRNEK VERİ rozeti kalksa bile bu şerit gerçek veriye S3'te kavuşur (dürüst
   rozet deseni, D-34: sahte-canlılık yasak). */
export function PresenceStrip() {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-border bg-card px-4 py-2.5">
      <span className="text-xs font-medium text-muted-foreground">
        Şu an{" "}
        <span className="rounded bg-muted px-1 py-0.5" title="GET /presence S3'te — Ek B1">
          (örnek — canlı S3'te)
        </span>
      </span>
      {mockPresence.map((p) => (
        <span key={p.handle} className="inline-flex items-center gap-1.5">
          <ActorChip handle={p.handle} />
          <span className="text-xs text-muted-foreground">
            → <span className="font-mono">{p.module}</span>
          </span>
        </span>
      ))}
    </div>
  );
}
