/* Güç-yönlü graf (#130 mod a) — "düğüm evreni": aktörler ve modüller aynı
   uzayda, aralarındaki dokunuş kenarları onları birbirine çeker.

   Isı matrisi "kim neye dokundu"yu SAYIYLA verir; bu görünüm aynı veriyi
   GEOMETRİ olarak verir: birbirine dokunan işler birbirine yakın düşer, iki
   aktörün ortasında kalan modül = kesişim riski (radar'ın baktığı şey).
   Sıfır yeni endpoint — kaynak aynı `GET /graph` cevabı.

   Yerleşim `lib/grafYerlesimi.ts`'te (saf + deterministik + test edilir);
   burada YALNIZCA çizim var. Kütüphane eklenmedi (bağımlılık yasağı).

   ── Renk tek kanal DEĞİL (tasarım paketi, D-34) ────────────────────────────
   Aktör = daire, modül = kare: TÜR ŞEKİLLE ayrılır, renkle değil. Ağırlık
   yarıçapa (√ölçek) ve düğümün yanındaki SAYIYA yazılır. `is_active_declared`
   kenar = kalın + kesikli-değil düz + `stroke-primary`, ayrıca düğümde halka.

   ── Erişilebilirlik ─────────────────────────────────────────────────────────
   SVG kendi başına ekran okuyucuya bir şey söylemez. Her düğüm gerçek bir
   `role="button"` + `tabIndex` + Enter/Space taşır (Isı matrisi'nin gerçek
   `<button>`larının SVG'deki karşılığı) ve grafın tamamının metin özeti
   `sr-only` bir listede ayrıca yazılıdır. Vurgulama fare-üstü İLE BİRLİKTE
   klavye odağında da tetiklenir — aksi halde sönme etkisi yalnız fareyle
   çalışan gizli bir özellik olurdu. */

import { useMemo, useState } from "react";
import type { components } from "../api/schema.d.ts";
import { ActorChip } from "./ui";
import { gucYonluYerlesim } from "../lib/grafYerlesimi";

type GraphEdge = components["schemas"]["GraphEdge"];

/** Nominal tuval — gerçek boyut ne olursa olsun viewBox oranı korur. */
const TUVAL_G = 1000;
const TUVAL_Y = 620;

/** İlgisiz düğüm/kenarın sönme oranı — #130 kabul kriteri: "hover'da ilgisiz
    düğümler %30'a söner". Literal: JIT değil, SVG opacity (sayı) olarak. */
const SONUK = 0.3;

export type GucDugumu = {
  id: string;
  tip: "aktor" | "modul";
  toplam: number;
  /** Yalnız modüller: birden fazla aktör dokundu mu (⇄ kesişim adayı). */
  paylasilan: boolean;
  /** Yalnız aktörler (#296): GitHub hesabıyla eşleşti mi. */
  dogrulandi: boolean;
};

/** Yerleşim/komşuluk anahtarı — aktör ve modül AD ALANI ayrılır.
    Neden: `id` tek başına benzersiz DEĞİL. `engine` adında bir GitHub
    kullanıcısı ile `engine` modülü aynı anda var olabilir; tek düzlemde
    saklarsak ikisi tek düğüme çöker ve kenarlar sessizce yanlış yere bağlanır.
    Nadir ama sessiz — tam da en pahalı hata türü. */
export function dugumAnahtari(tip: "aktor" | "modul", id: string): string {
  return `${tip === "aktor" ? "a" : "m"}:${id}`;
}

/** Ağırlık → yarıçap: √ölçek (alan ağırlıkla orantılı olsun; yarıçapı doğrudan
    ağırlığa bağlasak 40 dokunuşlu düğüm ekranı yerdi). */
function yaricap(toplam: number, enBuyuk: number): number {
  if (enBuyuk <= 0) return 10;
  return 9 + 17 * Math.sqrt(Math.max(toplam, 0) / enBuyuk);
}

export default function GucYonluGraf({
  dugumler,
  kenarlar,
  secili,
  onSec,
}: {
  dugumler: GucDugumu[];
  kenarlar: GraphEdge[];
  secili: string | null;
  onSec: (id: string) => void;
}) {
  // Fare-üstü VE klavye odağı aynı state'i besler (bkz. başlık notu).
  const [vurgulu, setVurgulu] = useState<string | null>(null);

  const yerlesim = useMemo(
    () =>
      gucYonluYerlesim(
        dugumler.map((d) => ({ id: dugumAnahtari(d.tip, d.id), agirlik: d.toplam })),
        kenarlar.map((e) => ({
          kaynak: dugumAnahtari("aktor", e.actor),
          hedef: dugumAnahtari("modul", e.module),
          agirlik: e.count,
        })),
        TUVAL_G,
        TUVAL_Y,
      ),
    [dugumler, kenarlar],
  );

  const konum = useMemo(() => new Map(yerlesim.map((k) => [k.id, k])), [yerlesim]);

  // Komşuluk: sönme kararı buradan. Kenarın İKİ ucu da komşudur.
  // Hem anahtar hem DEĞERLER ad-alanlı: ham id'yle karşılaştırsaydık aynı adlı
  // aktör/modül birbirinin komşusu sayılırdı (dugumAnahtari notundaki tuzak).
  const komsu = useMemo(() => {
    const m = new Map<string, Set<string>>();
    const ekle = (a: string, b: string) => {
      let s = m.get(a);
      if (!s) m.set(a, (s = new Set()));
      s.add(b);
    };
    for (const e of kenarlar) {
      const ak = dugumAnahtari("aktor", e.actor);
      const mk = dugumAnahtari("modul", e.module);
      ekle(ak, mk);
      ekle(mk, ak);
    }
    return m;
  }, [kenarlar]);

  const enBuyuk = useMemo(
    () => dugumler.reduce((m, d) => Math.max(m, d.toplam), 0),
    [dugumler],
  );

  // Odak = vurgulanan (fare/klavye) yoksa seçili. Seçim kalıcı, vurgu geçici.
  const odak = vurgulu ?? secili;
  const odakKomsulari = odak ? komsu.get(odak) : undefined;

  function belirginlik(anahtar: string): number {
    if (!odak) return 1;
    if (anahtar === odak) return 1;
    return odakKomsulari?.has(anahtar) ? 1 : SONUK;
  }

  function kenarBelirginligi(e: GraphEdge): number {
    if (!odak) return 1;
    return dugumAnahtari("aktor", e.actor) === odak ||
      dugumAnahtari("modul", e.module) === odak
      ? 1
      : SONUK;
  }

  return (
    <div className="rounded-lg border border-border bg-card">
      <svg
        viewBox={`0 0 ${TUVAL_G} ${TUVAL_Y}`}
        className="h-72 w-full sm:h-[26rem]"
        role="group"
        aria-label="Güç-yönlü dokunma grafı — aktörler ve modüller"
      >
        {/* Kenarlar önce: düğümlerin ALTINDA kalsınlar */}
        <g>
          {kenarlar.map((e) => {
            const a = konum.get(dugumAnahtari("aktor", e.actor));
            const b = konum.get(dugumAnahtari("modul", e.module));
            // Konumu olmayan uç = `nodes`ta geçmeyen kenar; çizilmez (uydurma
            // koordinat üretmektense kenarı atlamak dürüst olan).
            if (!a || !b) return null;
            return (
              <line
                key={`${e.actor}→${e.module}`}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                opacity={kenarBelirginligi(e)}
                strokeWidth={e.is_active_declared ? 3 : 1.25}
                className={
                  e.is_active_declared ? "stroke-primary" : "stroke-muted-foreground/45"
                }
              />
            );
          })}
        </g>

        <g>
          {dugumler.map((d) => {
            const anahtar = dugumAnahtari(d.tip, d.id);
            const k = konum.get(anahtar);
            if (!k) return null;
            const r = yaricap(d.toplam, enBuyuk);
            const op = belirginlik(anahtar);
            const isSecili = secili === anahtar;
            const etiket =
              d.tip === "aktor"
                ? `Aktör ${d.id}, ${d.toplam} dokunuş`
                : `Modül ${d.id}, ${d.toplam} dokunuş${
                    d.paylasilan ? ", birden fazla aktör dokundu" : ""
                  }`;
            return (
              <g
                key={anahtar}
                role="button"
                tabIndex={0}
                aria-label={etiket}
                aria-pressed={isSecili}
                className="cursor-pointer focus:outline-none"
                opacity={op}
                onClick={() => onSec(anahtar)}
                onKeyDown={(ev) => {
                  if (ev.key === "Enter" || ev.key === " ") {
                    ev.preventDefault();
                    onSec(anahtar);
                  }
                }}
                onMouseEnter={() => setVurgulu(anahtar)}
                onMouseLeave={() => setVurgulu(null)}
                onFocus={() => setVurgulu(anahtar)}
                onBlur={() => setVurgulu(null)}
              >
                {/* Aktör = daire, modül = kare (şekil kanalı — renk tek başına değil) */}
                {d.tip === "aktor" ? (
                  <circle
                    cx={k.x}
                    cy={k.y}
                    r={r}
                    className={`fill-primary/70 ${
                      isSecili ? "stroke-foreground" : "stroke-background"
                    }`}
                    strokeWidth={isSecili ? 3 : 1.5}
                  />
                ) : (
                  <rect
                    x={k.x - r}
                    y={k.y - r}
                    width={r * 2}
                    height={r * 2}
                    rx={4}
                    className={`fill-muted-foreground/55 ${
                      isSecili ? "stroke-foreground" : "stroke-background"
                    }`}
                    strokeWidth={isSecili ? 3 : 1.5}
                  />
                )}
                {/* Kesişim adayı modül: halka (⇄'in geometrideki karşılığı) */}
                {d.tip === "modul" && d.paylasilan && (
                  <rect
                    x={k.x - r - 4}
                    y={k.y - r - 4}
                    width={r * 2 + 8}
                    height={r * 2 + 8}
                    rx={6}
                    fill="none"
                    strokeWidth={2}
                    className="stroke-foreground/70"
                  />
                )}
                <text
                  x={k.x}
                  y={k.y + r + 13}
                  textAnchor="middle"
                  className="pointer-events-none fill-foreground font-mono text-[13px]"
                >
                  {d.id.length > 18 ? `${d.id.slice(0, 17)}…` : d.id}
                </text>
                <text
                  x={k.x}
                  y={k.y + 4}
                  textAnchor="middle"
                  className="pointer-events-none fill-background text-[12px] font-semibold"
                >
                  {d.toplam}
                </text>
              </g>
            );
          })}
        </g>
      </svg>

      {/* Grafın metin karşılığı: SVG'yi okuyamayan için tam döküm.
          Komşu anahtarları ad-alanlı tutuluyor, basarken önek atılır. */}
      <ul className="sr-only">
        {dugumler.map((d) => (
          <li key={dugumAnahtari(d.tip, d.id)}>
            {d.tip === "aktor" ? "Aktör" : "Modül"} {d.id}: {d.toplam} dokunuş,{" "}
            {[...(komsu.get(dugumAnahtari(d.tip, d.id)) ?? [])]
              .map((a) => a.slice(2))
              .join(", ") || "bağlantısız"}
          </li>
        ))}
      </ul>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-border px-3 py-2 text-[11px] text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <svg width="12" height="12" aria-hidden>
            <circle cx="6" cy="6" r="5" className="fill-primary/70" />
          </svg>
          aktör
        </span>
        <span className="inline-flex items-center gap-1.5">
          <svg width="12" height="12" aria-hidden>
            <rect width="12" height="12" rx="2" className="fill-muted-foreground/55" />
          </svg>
          modül
        </span>
        <span className="inline-flex items-center gap-1.5">
          <svg width="20" height="6" aria-hidden>
            <line x1="0" y1="3" x2="20" y2="3" strokeWidth="3" className="stroke-primary" />
          </svg>
          şu an beyanlı kenar
        </span>
        <span>alan = dokunuş sayısı · üstüne gel: ilgisizler soluklaşır</span>
      </div>
    </div>
  );
}

/** Seçili düğümün sağ paneli — Isı matrisi'nin `KenarPaneli`'yle aynı ölçü
    ve dil, ama tek kenar değil düğümün TÜM komşuları. */
export function DugumPaneli({
  dugum,
  komsular,
  aktorDogrulandi,
  onClose,
}: {
  dugum: GucDugumu;
  komsular: { id: string; count: number; is_active_declared: boolean }[];
  aktorDogrulandi: Map<string, boolean>;
  onClose: () => void;
}) {
  const aktorMu = dugum.tip === "aktor";
  return (
    <aside
      aria-label="Düğüm detayı"
      className="sticky top-0 flex max-h-[calc(100vh-7rem)] w-[380px] shrink-0 flex-col gap-4 self-start overflow-y-auto rounded-lg border border-border bg-card p-4"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1.5">
          {aktorMu ? (
            <ActorChip handle={dugum.id} verified={dugum.dogrulandi} />
          ) : (
            <p className="truncate font-mono text-sm font-semibold">{dugum.id}</p>
          )}
          <p className="text-[11px] text-muted-foreground">
            {aktorMu ? "aktör" : "modül"} · {dugum.toplam} dokunuş
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Detayı kapat"
          className="rounded px-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          ✕
        </button>
      </div>

      {dugum.tip === "modul" && dugum.paylasilan && (
        <p className="rounded border border-primary/40 bg-primary/10 px-2 py-1.5 text-xs">
          <span aria-hidden>⇄ </span>Bu modüle birden fazla aktör dokundu —
          kesişim riski burada.
        </p>
      )}

      <div className="space-y-2.5">
        <h3 className="text-[11px] font-semibold tracking-wide text-muted-foreground">
          {aktorMu ? "Dokunduğu modüller" : "Kim dokunuyor"}
        </h3>
        <ul className="space-y-2">
          {komsular.map((n) => (
            <li
              key={n.id}
              className="flex items-center justify-between gap-2 rounded border border-border px-2 py-1.5"
            >
              {aktorMu ? (
                <span className="min-w-0 truncate font-mono text-xs">{n.id}</span>
              ) : (
                <ActorChip handle={n.id} verified={aktorDogrulandi.get(n.id) ?? true} />
              )}
              <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                {n.is_active_declared && (
                  <span title="Şu an .harness/active'da beyanlı" aria-hidden>
                    ◎
                  </span>
                )}
                <span className="tabular-nums">{n.count}</span>
              </span>
            </li>
          ))}
        </ul>
      </div>

      <div className="mt-auto space-y-1.5 border-t border-border pt-3">
        <p className="text-[10px] leading-snug text-muted-foreground">
          Yerleşim deterministik: aynı veri her zaman aynı resmi verir (rastgele
          tohum yok). Yakınlık dokunuş ilişkisini gösterir, mesafe bir birim
          taşımaz.
        </p>
        <p className="font-mono text-[10px] text-muted-foreground">Esc kapat</p>
      </div>
    </aside>
  );
}
