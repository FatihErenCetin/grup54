import type { components } from "../api/schema.d.ts";
import { moduleOf } from "./FeedItem";
import { ActorChip, ConfidenceMeter, SeverityBadge } from "./ui";

type Detection = components["schemas"]["Detection"];

/* Sağdan detay paneli (#156 — Pencil node MOGXv'ye sadakat, PR #150'de
   gate'lenen parça PO kararıyla öne çekildi).
   Tasarımdan bilinçli farklar (dürüstlük, D-34):
   - Aksiyon butonları (Gördüm/Yanlış alarm/Ertele) YOK — yazma ucu Ek B6/S3;
     tıklanıp iş yapmayan buton basılmaz. Yerinde gate notu var.
   - Sinyaller kutusunda "hunk örtüşmesi" satırı YOK — o veri Detection'da
     henüz taşınmıyor; uydurma sinyal yazılmaz.
   - "/radar?d=<id>" deep-link ipucu YOK — link davranışı S3 cilası. */
export function DetailSheet({
  detection,
  onClose,
}: {
  detection: Detection;
  onClose: () => void;
}) {
  const modul = moduleOf(detection.files);
  return (
    // sticky + max-h + iç scroll: 50 dosyalı tespit viewport'u aşıyordu ve
    // ok-tuşu preventDefault'u ana scroll'u kilitliyordu (doğrulama ölçümü)
    <aside
      id="detay-paneli"
      aria-label="Tespit detayı"
      className="sticky top-0 flex max-h-[calc(100vh-7rem)] w-[380px] shrink-0 flex-col gap-4 self-start overflow-y-auto rounded-lg border border-border bg-card p-4"
    >
      <div className="flex items-center justify-between gap-3">
        <SeverityBadge level={detection.severity} />
        <span className="flex items-center gap-3">
          <ConfidenceMeter value={detection.confidence} />
          <button
            type="button"
            onClick={onClose}
            aria-label="Detayı kapat"
            className="rounded px-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            ✕
          </button>
        </span>
      </div>

      <p className="text-sm leading-relaxed">{detection.rationale}</p>

      <div className="space-y-2.5">
        <h3 className="text-[11px] font-semibold tracking-wide text-muted-foreground">
          DOSYALAR
        </h3>
        <ul className="space-y-1 font-mono text-xs">
          {detection.files.map((f) => (
            <li key={f} className="truncate" title={f}>
              {f}
            </li>
          ))}
        </ul>
      </div>

      <div className="space-y-2.5">
        <h3 className="text-[11px] font-semibold tracking-wide text-muted-foreground">
          BRANCH'LER · AKTÖRLER
        </h3>
        <div className="flex flex-wrap gap-1.5">
          {detection.branches.map((b) => (
            <code
              key={b}
              title={b}
              className="inline-block max-w-full truncate rounded bg-muted px-1.5 py-0.5 align-bottom font-mono text-xs"
            >
              {b}
            </code>
          ))}
        </div>
        <div className="flex flex-wrap gap-3">
          {detection.actors.map((a) => (
            <ActorChip key={a} handle={a} />
          ))}
        </div>
      </div>

      <div className="space-y-1.5 rounded-lg border border-border bg-background p-3">
        <h3 className="text-[11px] font-semibold tracking-wide text-muted-foreground">
          DETERMİNİSTİK SİNYALLER
        </h3>
        <p className="font-mono text-[11px] leading-relaxed">
          çakışan dosya: {detection.files.length} · modül: {modul}
          <br />
          confidence: %{Math.round(detection.confidence * 100)}
        </p>
      </div>

      <div className="mt-auto space-y-1.5 border-t border-border pt-3">
        <p className="text-[10px] leading-snug text-muted-foreground">
          Aksiyonlar (Gördüm · Yanlış alarm · Ertele) S3'te gelir — yazma ucu Ek
          B6 ertelemesi; iş yapmayan buton basmıyoruz.
        </p>
        <p className="font-mono text-[10px] text-muted-foreground">
          ↑↓ gezin · Esc kapat
        </p>
      </div>
    </aside>
  );
}
