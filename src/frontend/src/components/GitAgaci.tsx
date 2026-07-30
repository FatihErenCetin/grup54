/* Git ağacı — şerit görünümü (#130 mod d).
 *
 * ── Bu bir commit DAG'ı DEĞİL, ve öyleymiş gibi de yapmıyor ────────────────
 * Gerçek ağaç (ebeveyn→çocuk okları, merge dirsekleri) `parent_sha` ister;
 * `NormalizedEvent` bunu taşımıyor (Ek-B B6 ertelemesi). Uydurma bir ağaç
 * çizmek, eksik bir görünümden çok daha pahalıya patlar: kullanıcı çizilen
 * dirseğe İNANIR. Bu yüzden çizilen şey kontratın gerçekten taşıdığı bilgi:
 *   dal başına bir ŞERİT + o şeritteki olayların ZAMAN sırası
 * ve bu sınır ekranın üstünde GÖRÜNÜR bir cümle olarak yazılı — sadece kod
 * yorumunda değil (kullanıcı kod yorumu okumaz).
 *
 * #130'un kendi tanımı da zaten buydu: "şerit-temelli … NormalizedEvent'ten
 * deterministik, kontrat eki GEREKMEZ".
 *
 * ── Radar çapraz-linki (#130 kabul kriteri) ────────────────────────────────
 * Çakışma ADAYI = birden fazla şeritte geçen dosya. Bu, radar'ın baktığı
 * sinyalin ta kendisi (iki iş aynı dosyaya dokunuyor), ama radar'ın VERDİĞİ
 * karar değil — orada Gemini judge + eşik var. Bu yüzden etiket "çakışma"
 * değil "çakışma adayı", ve link kullanıcıyı gerçek kararın olduğu yere
 * (Radar) götürür. Radar bugün derin-link (seçili tespit) desteklemiyor;
 * link sayfanın kendisine gider, sahte bir sorgu parametresi uydurmuyoruz. */

import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ActorChip, EmptyState } from "./ui";
import {
  altSatirAta,
  seritDizilimi,
  zamanYuzdesi,
  type SeritOlayi,
  type YerlesikOlay,
} from "../lib/grafYerlesimi";

/** Alt-satır yüksekliği (px) — üst üste binen noktalar bu kadar aşağı kayar. */
const ALT_SATIR_PX = 17;

const TIP_ETIKETI: Record<SeritOlayi["tip"], string> = {
  commit: "commit",
  pr: "PR",
  issue: "issue",
  branch: "dal",
};

/** Olay tipi ŞEKİLLE ayrılır (renk tek kanal değil — D-34):
    commit = daire · PR = eşkenar dörtgen (45° kare) · issue = kare · dal = çubuk. */
function tipSekli(tip: SeritOlayi["tip"]): string {
  switch (tip) {
    case "pr":
      return "size-3 rotate-45 rounded-[2px]";
    case "issue":
      return "size-2.5 rounded-[2px]";
    case "branch":
      return "h-3.5 w-1.5 rounded-[1px]";
    default:
      return "size-2.5 rounded-full";
  }
}

function tarihKisa(t: number): string {
  return new Date(t).toLocaleDateString("tr-TR", { day: "2-digit", month: "short" });
}

function tarihTam(t: number): string {
  return new Date(t).toLocaleString("tr-TR");
}

/** Varsayılan şerit üst sınırı. Canlı ölçüm (30 Tem 2026): 14 günlük
    pencerede 130 şerit, 82'si tek olaylı → hepsini çizmek sayfayı yer. */
const VARSAYILAN_SERIT_SINIRI = 12;

export default function GitAgaci({ olaylar }: { olaylar: SeritOlayi[] }) {
  const [secili, setSecili] = useState<YerlesikOlay | null>(null);
  const [hepsiniGoster, setHepsiniGoster] = useState(false);
  const dizilim = useMemo(
    () => seritDizilimi(olaylar, hepsiniGoster ? Infinity : VARSAYILAN_SERIT_SINIRI),
    [olaylar, hepsiniGoster],
  );
  const { seritler, bas, son, cakisanDosyalar, okunamayan, gizlenenSerit, gizlenenOlay } =
    dizilim;

  // Panel "Esc kapat" YAZIYORSA Esc gerçekten kapatmalı — GraphPage'in kendi
  // panelleriyle aynı kural (yazılı vaat, bağlanmış davranış).
  useEffect(() => {
    if (!secili) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSecili(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [secili]);

  // Her şerit için alt-satır ataması — üst üste binen noktalar açılsın.
  const altSatirlar = useMemo(
    () =>
      seritler.map((s) =>
        altSatirAta(s.olaylar.map((o) => zamanYuzdesi(o.t, bas, son))),
      ),
    [seritler, bas, son],
  );

  if (seritler.length === 0) {
    return (
      <EmptyState
        title="Bu akışta çizilecek olay yok"
        description="Git şeridi, izlenen commit/PR/issue olaylarından (GET /events) doğrudan türer."
        items={[
          "Satır = dal (şerit), yatay eksen = zaman",
          "Nokta = olay; eşkenar dörtgen = PR",
          "Halkalı nokta = dosyasına başka bir dalda da dokunulmuş (çakışma adayı)",
        ]}
        eta={
          okunamayan > 0
            ? `${okunamayan} olayın tarihi okunamadı, çizilmedi.`
            : "Olaylar ingest'ten gelir (#52)."
        }
      />
    );
  }

  const toplamOlay = seritler.reduce((s, x) => s + x.olaylar.length, 0);

  return (
    <div className="flex items-start gap-4">
      <div className="min-w-0 flex-1 space-y-3">
        {/* Sınırın kendisi: kod yorumunda değil, kullanıcının gözünün önünde. */}
        <p className="rounded border border-border bg-muted/30 px-2.5 py-2 text-[11px] leading-relaxed text-muted-foreground">
          <span className="font-medium text-foreground">Bu bir commit ağacı (DAG) değil.</span>{" "}
          Ebeveyn–çocuk bağı (<code className="font-mono">parent_sha</code>) bugünkü olay
          kontratında yok, o yüzden ok/dirsek <em>çizilmiyor</em> — uydurulmuyor. Çizilen:
          her dal bir şerit, yatay eksen gerçek zaman.
        </p>

        <p className="text-xs text-muted-foreground">
          <span className="tabular-nums">{seritler.length}</span> şerit ·{" "}
          <span className="tabular-nums">{toplamOlay}</span> olay ·{" "}
          <span className="tabular-nums">{cakisanDosyalar.size}</span> dosyaya birden
          fazla dalda dokunulmuş
          {okunamayan > 0 && (
            <>
              {" · "}
              <span className="text-foreground">
                <span className="tabular-nums">{okunamayan}</span> olay tarihi okunamadığı
                için çizilmedi
              </span>
            </>
          )}
        </p>

        {/* Gizli üst sınır YOK: kırpıldıysa kaçının kırpıldığı yazılır ve
            tamamına ulaşmanın yolu hep açık kalır. */}
        {gizlenenSerit > 0 && (
          <p className="flex flex-wrap items-center gap-2 text-xs">
            <span className="text-muted-foreground">
              En hareketli{" "}
              <span className="tabular-nums">{seritler.length}</span> şerit gösteriliyor;{" "}
              <span className="tabular-nums text-foreground">{gizlenenSerit}</span> şerit
              (<span className="tabular-nums">{gizlenenOlay}</span> olay) gizli.
            </span>
            <button
              type="button"
              onClick={() => setHepsiniGoster(true)}
              className="rounded border border-border px-2 py-0.5 text-[11px] font-medium hover:bg-muted"
            >
              Tümünü göster
            </button>
          </p>
        )}
        {hepsiniGoster && (
          <p className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span>Tüm şeritler gösteriliyor.</span>
            <button
              type="button"
              onClick={() => setHepsiniGoster(false)}
              className="rounded border border-border px-2 py-0.5 text-[11px] font-medium hover:bg-muted"
            >
              En hareketli {VARSAYILAN_SERIT_SINIRI}'ye dön
            </button>
          </p>
        )}

        <div className="overflow-x-auto rounded-lg border border-border bg-card">
          <div className="min-w-[640px] p-3">
            {/* Zaman ekseni başlığı */}
            <div className="mb-2 flex items-center gap-3 border-b border-border pb-1.5">
              <span className="w-40 shrink-0 text-[11px] font-medium text-muted-foreground">
                Dal
              </span>
              <span className="flex flex-1 justify-between font-mono text-[10px] text-muted-foreground">
                <span>{bas !== null ? tarihKisa(bas) : ""}</span>
                <span>zaman →</span>
                <span>{son !== null ? tarihKisa(son) : ""}</span>
              </span>
            </div>

            {seritler.map((serit, si) => {
              const satirlar = altSatirlar[si];
              const enAlt = satirlar.length > 0 ? Math.max(...satirlar) : 0;
              return (
                <div key={serit.dal} className="flex items-start gap-3 py-1">
                  <span
                    title={
                      serit.dalBilinmiyor
                        ? // Ölçüm (canlı, 30 Tem 2026): 378 commit + 193 issue dalsız.
                          // Kullanıcı bunu bir HATA sanmasın diye sebebi yazılı.
                          "Bu olaylar dal bilgisi taşımıyor: issue'ların dalı yoktur, commit'ler de varsayılan daldan (sha=main) çekildiği için dal atfı gelmez. Bir hata değil, kaynağın sınırı."
                        : serit.dal
                    }
                    className={`w-40 shrink-0 truncate pt-1 font-mono text-[11px] ${
                      serit.dalBilinmiyor
                        ? "italic text-muted-foreground"
                        : "text-foreground"
                    }`}
                  >
                    {serit.dal}
                    {serit.dalBilinmiyor && (
                      <span aria-hidden className="ml-1 not-italic">
                        ⓘ
                      </span>
                    )}
                  </span>
                  <div
                    className="relative flex-1"
                    style={{ height: (enAlt + 1) * ALT_SATIR_PX + 6 }}
                  >
                    {/* Şerit çizgisi — dalın kendisi (bağ değil, sadece kulvar) */}
                    <div
                      aria-hidden
                      className="absolute inset-x-0 top-1.5 h-px bg-border"
                    />
                    {serit.olaylar.map((o, oi) => {
                      const x = zamanYuzdesi(o.t, bas, son);
                      const cakisiyor = o.cakisan.length > 0;
                      const isSecili = secili?.id === o.id;
                      return (
                        <button
                          key={o.id}
                          type="button"
                          aria-pressed={isSecili}
                          onClick={() =>
                            setSecili((s) => (s?.id === o.id ? null : o))
                          }
                          title={`${TIP_ETIKETI[o.tip]} · ${o.aktor} · ${tarihTam(
                            o.t,
                          )}${cakisiyor ? ` · ${o.cakisan.length} çakışma adayı dosya` : ""}`}
                          style={{
                            left: `${x}%`,
                            top: satirlar[oi] * ALT_SATIR_PX,
                          }}
                          className="absolute -translate-x-1/2 cursor-pointer p-1"
                        >
                          <span
                            aria-hidden
                            className={`block ${tipSekli(o.tip)} ${
                              cakisiyor
                                ? "bg-severity-med ring-2 ring-foreground/70"
                                : "bg-primary/70"
                            } ${isSecili ? "outline outline-2 outline-offset-2 outline-foreground" : ""}`}
                          />
                          <span className="sr-only">
                            {serit.dal} dalında {TIP_ETIKETI[o.tip]}, {o.aktor},{" "}
                            {tarihTam(o.t)}
                            {cakisiyor
                              ? `, ${o.cakisan.length} dosyasına başka dalda da dokunuldu`
                              : ""}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <span aria-hidden className="inline-block size-2.5 rounded-full bg-primary/70" />
            commit
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span
              aria-hidden
              className="inline-block size-3 rotate-45 rounded-[2px] bg-primary/70"
            />
            PR
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span
              aria-hidden
              className="inline-block size-2.5 rounded-full bg-severity-med ring-2 ring-foreground/70"
            />
            çakışma adayı (dosyasına başka dalda da dokunulmuş)
          </span>
          <span>dikey konum anlamsız — yalnız üst üste binmeyi açar</span>
        </div>
      </div>

      {secili && (
        <OlayPaneli olay={secili} onClose={() => setSecili(null)} />
      )}
    </div>
  );
}

function OlayPaneli({ olay, onClose }: { olay: YerlesikOlay; onClose: () => void }) {
  const cakisan = new Set(olay.cakisan);
  return (
    <aside
      aria-label="Olay detayı"
      className="sticky top-0 flex max-h-[calc(100vh-7rem)] w-[380px] shrink-0 flex-col gap-4 self-start overflow-y-auto rounded-lg border border-border bg-card p-4"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1.5">
          <ActorChip handle={olay.aktor} verified={olay.dogrulandi} />
          <p className="truncate font-mono text-xs">{olay.ref}</p>
          <p className="text-[11px] text-muted-foreground">
            {TIP_ETIKETI[olay.tip]} · {olay.dal ?? "dal bilgisi yok"} ·{" "}
            {tarihTam(olay.t)}
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

      {olay.cakisan.length > 0 && (
        <div className="space-y-2 rounded border border-primary/40 bg-primary/10 px-2.5 py-2">
          <p className="text-xs leading-relaxed">
            <span aria-hidden>⇄ </span>
            <span className="tabular-nums">{olay.cakisan.length}</span> dosyasına{" "}
            <strong>başka bir dalda da</strong> dokunulmuş — çakışma adayı.
          </p>
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            Bu bir tespit değil, sinyal: gerçek değerlendirme (kesişim + judge +
            eşik) Radar'da.
          </p>
          <Link
            to="/radar"
            className="inline-block rounded border border-border px-2 py-1 text-[11px] font-medium hover:bg-muted"
          >
            Radar'da incele →
          </Link>
        </div>
      )}

      <div className="space-y-2.5">
        <h3 className="text-[11px] font-semibold tracking-wide text-muted-foreground">
          Dokunulan dosyalar ({olay.files.length})
        </h3>
        {olay.files.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            Bu olay dosya listesi taşımıyor (örn. issue).
          </p>
        ) : (
          <ul className="space-y-1">
            {olay.files.map((f) => (
              <li
                key={f}
                className={`truncate rounded px-1.5 py-1 font-mono text-[11px] ${
                  cakisan.has(f)
                    ? "bg-primary/10 text-foreground"
                    : "text-muted-foreground"
                }`}
                title={f}
              >
                {cakisan.has(f) && <span aria-hidden>⇄ </span>}
                {f}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="mt-auto space-y-1.5 border-t border-border pt-3">
        <p className="text-[10px] leading-snug text-muted-foreground">
          Ebeveyn commit bağı gösterilmiyor: <code className="font-mono">parent_sha</code>{" "}
          olay kontratında yok. Şerit = dal, yatay konum = gerçek zaman.
        </p>
        <p className="font-mono text-[10px] text-muted-foreground">Esc kapat</p>
      </div>
    </aside>
  );
}
