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
   [severity][rationale 1 cümle][aktörler][modül çipi][confidence].
   Tıklama = SEÇİM → sağdan DetailSheet (#156, Pencil MOGXv); accordion
   kaldırıldı (tasarıma dönüş). Gate'li kalanlar: yaş (Ek B1 S3) · aksiyon
   butonları (Ek B6). */
export function FeedItem({
  detection,
  selected = false,
  onSelect,
  bindRef,
}: {
  detection: Detection;
  selected?: boolean;
  onSelect: (d: Detection) => void;
  /** Klavye gezinmesinde focus'un seçimi takip etmesi için (roving) */
  bindRef?: (el: HTMLButtonElement | null) => void;
}) {
  return (
    <li
      className={`rounded-lg border bg-card ${
        selected ? "border-foreground/25" : "border-border"
      }`}
    >
      {/* disclosure deseni: satır yan bölgeyi açar/kapatır (pressed değil) */}
      <button
        ref={bindRef}
        type="button"
        onClick={() => onSelect(detection)}
        aria-expanded={selected}
        aria-controls="detay-paneli"
        className={`flex w-full items-center gap-3 px-4 py-3 text-left ${
          selected ? "bg-muted" : "hover:bg-muted/40"
        }`}
      >
        <SeverityBadge level={detection.severity} />
        <span className="min-w-0 flex-1 truncate text-sm" title={detection.rationale}>
          {detection.rationale}
        </span>
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
    </li>
  );
}
