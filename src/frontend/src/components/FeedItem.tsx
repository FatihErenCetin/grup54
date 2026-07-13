import { useState } from "react";
import type { components } from "../api/schema.d.ts";
import { ActorChip, ConfidenceMeter, SeverityBadge } from "./ui";

type Detection = components["schemas"]["Detection"];

/** Dosya yolundan modül etiketi — çip için kaba ama okunur sınıflama. */
export function moduleOf(files: string[]): string {
  const first = files[0] ?? "";
  if (first.startsWith("src/backend/ensemble/")) {
    const seg = first.split("/")[3] ?? "";
    // paket kökündeki dosya (config.py gibi) modül değil → genel etiket
    return seg && !seg.includes(".") ? seg : "backend";
  }
  if (first.startsWith("src/frontend/")) return "frontend";
  if (first.startsWith(".github/")) return "ci";
  if (first.startsWith("docs/")) return "docs";
  if (first.startsWith("eval/")) return "eval";
  return first.includes("/") ? (first.split("/")[0] ?? "repo") : "repo";
}

/* Radar satır anatomisi (#21, tasarım paketi /radar):
   [severity][rationale 1 cümle][aktörler][modül çipi][confidence] + expand.
   Gate'li (bilinçli yok — Ek B1/B7): yaş göstergesi (first_seen_at S3) ·
   aksiyon butonları (yazma ucu S3-sonrası) · side-sheet (S2 cila sınırı). */
export function FeedItem({ detection }: { detection: Detection }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="rounded-lg border border-border bg-card">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-muted/40"
      >
        <SeverityBadge level={detection.severity} />
        <span className="min-w-0 flex-1 truncate text-sm">{detection.rationale}</span>
        <span className="flex shrink-0 items-center gap-2">
          {detection.actors.map((a, i) => (
            <ActorChip key={`${a}-${i}`} handle={a} />
          ))}
        </span>
        <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground">
          {moduleOf(detection.files)}
        </span>
        <ConfidenceMeter value={detection.confidence} />
      </button>
      {open && (
        <div className="space-y-2 border-t border-border px-4 py-3 text-sm">
          <p className="text-muted-foreground">{detection.rationale}</p>
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs">
            <span>
              <span className="text-muted-foreground">Branch'ler: </span>
              {detection.branches.map((b) => (
                <code key={b} className="mr-2 rounded bg-muted px-1 py-0.5 font-mono">
                  {b}
                </code>
              ))}
            </span>
          </div>
          <ul className="space-y-0.5 font-mono text-xs text-muted-foreground">
            {detection.files.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        </div>
      )}
    </li>
  );
}
