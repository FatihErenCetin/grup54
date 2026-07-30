import { useState, type ReactNode } from "react";
import type { components } from "../api/schema.d.ts";
import { EmptyState, SonGuncelleme, YuklemeIskeleti } from "../components/ui";
import { ASK_MAX_LENGTH, useAsk } from "../lib/useAsk";

type QueryResponse = components["schemas"]["QueryResponse"];
type Citation = components["schemas"]["Citation"];
type CitationType = Citation["type"];

/* /ask — "Projeye sor" (tasarım paketi §2: tam genişlik soru kutusu + cevap
   bloğu + ZORUNLU citations listesi; boş durum = zaten davetkâr soru kutusu).

   Bu sayfanın iki bilinçli farkı var:

   1) HATA METNİ ÇEVRİLİR, HAM GÖVDE BASILMAZ. Uç bugün 503 dönüyor (Gemini
      kotası bitti; Groq gelince düzelir) ve bulunmuş bug tam olarak buydu:
      sağlayıcının ham 429/503 JSON'u kullanıcıya gidiyordu. Burada hata
      backend'in `ErrorEnvelope`ından (error/message/status — api/errors.py)
      okunup ANLAŞILIR TR mesaja çevrilir; ham gövde yerine tek satırlık,
      kısaltılmış teknik künye (`kod · HTTP 503`) basılır. Hata YUTULMAZ,
      yalnız *sindirilir* — teşhis için künye görünür kalır.
   2) Hata tüm sayfayı DEĞİL yalnız cevap alanını kaplar (HataDurumu tam-sayfa
      boş-durum kalıbıdır); soru kutusu ayakta kalmalı ki kullanıcı başka bir
      soruyla devam edebilsin.

   Gate'li (eksik DEĞİL, bilinçli): "Yeniden dene" butonu YOK — usePolling
   `refetch` döndürmüyor, aynı soru cache'ten gelirdi; iş yapmayan buton
   basmıyoruz (DetailSheet'teki aynı kural). Soru değişince yeni istek gider. */

const ORNEK_SORULAR = [
  "Son 3 gün içinde ne değişti?",
  "Auth modülüne kim dokundu?",
  "Hosted demo kararı neydi?",
  "Sprint 3 kapsamında neler var?",
];

const TUR_ETIKET: Record<CitationType, string> = {
  scope: "kapsam",
  task: "görev",
  decision: "karar",
  event: "olay",
  pr: "PR",
};

const GUVEN_ETIKET: Record<QueryResponse["confidence"], string> = {
  low: "düşük güven",
  medium: "orta güven",
  high: "yüksek güven",
};

/* ── Hata çevirisi ────────────────────────────────────────────────────────── */

type Zarf = { kod: string; durum: number; mesaj: string };

/** Backend'in tek-tip hata zarfı (api/errors.py ErrorEnvelope): {error,message,status}. */
function zarfOku(hata: unknown): Zarf | null {
  if (typeof hata !== "object" || hata === null) return null;
  const o = hata as { error?: unknown; message?: unknown; status?: unknown };
  if (typeof o.status !== "number" || typeof o.error !== "string") return null;
  return {
    kod: o.error,
    durum: o.status,
    mesaj: typeof o.message === "string" ? o.message : "",
  };
}

/** ISO zaman damgasını yerel saate çevirir; bozuk değer sessizce "Invalid Date"
    olmaz, ham metin basılır (ScopePage `zaman` · GraphPage `tarihMetni` ile aynı
    kalıp — uydurmak yerine dürüst ham veri). */
function zaman(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("tr-TR");
}

function tekSatir(metin: string, sinir = 140): string {
  const duz = metin.replace(/\s+/g, " ").trim();
  return duz.length > sinir ? `${duz.slice(0, sinir)}…` : duz;
}

/** Teknik künye: teşhis için YETER, ham gövde DEĞİL. Zarf varsa kod+status;
    yoksa tek satıra indirgenmiş, kısaltılmış özet. `hataMesaji`'yi bilerek
    kullanmıyoruz: zarf olmayan nesnelerde JSON.stringify'a düşüyor — yani
    tam da kullanıcıya sızan ham gövde. */
function teknikKunye(hata: unknown): string {
  const zarf = zarfOku(hata);
  if (zarf) return `${zarf.kod} · HTTP ${zarf.durum}`;
  if (hata instanceof Error) return tekSatir(hata.message);
  if (typeof hata === "string") {
    if (hata === "") return "(boş hata gövdesi)";
    // Proxy/CDN JSON yerine HTML hata sayfası döndürebilir — sayfayı basmak yerine söyle
    if (/^\s*</.test(hata)) return "sunucudan JSON zarf değil, HTML gövde döndü";
    return tekSatir(hata);
  }
  return "sunucudan beklenmeyen biçimde hata gövdesi geldi";
}

/** Zarf koduna → duruma → bağlantı hatasına doğru daralan çeviri. */
function hataMetni(hata: unknown): { baslik: string; aciklama: string } {
  const zarf = zarfOku(hata);
  if (!zarf) {
    return {
      baslik: "Backend'e ulaşılamadı",
      aciklama:
        "Sunucu cevap vermedi — `make dev` çalışıyor mu ve VITE_API_BASE_URL doğru mu kontrol et.",
    };
  }

  // Önce KOD (api/errors.py _DOMAIN_MAP): aynı 503 iki farklı şeyi anlatabiliyor
  switch (zarf.kod) {
    case "gemini_unavailable":
    case "ollama_unavailable":
      return {
        baslik: "AI değerlendirici şu an erişilemiyor",
        aciklama:
          "Cevabı üreten model geçici olarak yanıt vermiyor (kota ya da erişim). Birkaç dakika sonra tekrar sor — Radar, Board ve Kapsam sayfaları bu uçtan bağımsız çalışmaya devam ediyor.",
      };
    case "query_retrieval_unavailable":
      return {
        baslik: "Proje bağlamı şu an aranamıyor",
        aciklama:
          "Soru modele hiç gitmedi: kanonik bağlam (.harness + repo geçmişi) okunamadı. Model değil, arama katmanı erişilemez durumda.",
      };
    case "query_judge_error":
      return {
        baslik: "Cevap kanıta bağlanamadı",
        aciklama:
          "Model bir cevap üretti ama alıntıları kanonik kaynaklarla eşleşmedi; kaynaksız cevap göstermiyoruz. Soruyu biraz daha somut yazmayı dene.",
      };
    case "demo_rate_limited":
      return {
        baslik: "Demo istek limiti doldu",
        aciklama:
          "Bu hosted demo maliyet kapağı için istek sayısını sınırlıyor. Birkaç dakika bekleyip tekrar sor.",
      };
    case "query_invalid":
      return {
        baslik: "Soru işlenemedi",
        aciklama: `Soru boş olamaz ve en fazla ${ASK_MAX_LENGTH} karakter olabilir.`,
      };
  }

  // Kod tanınmadıysa duruma düş (yeni bir sağlayıcı hatası eklenirse sessiz kalmasın)
  if (zarf.durum === 429)
    return {
      baslik: "Demo istek limiti doldu",
      aciklama: "Çok sık soruldu — birkaç dakika bekleyip tekrar dene.",
    };
  if (zarf.durum === 503)
    return {
      baslik: "AI değerlendirici şu an erişilemiyor",
      aciklama:
        "Uç geçici olarak yanıt veremiyor. Kendiliğinden düzelebilir bir durum; birkaç dakika sonra tekrar sor.",
    };
  if (zarf.durum === 502)
    return {
      baslik: "AI sağlayıcısı isteği reddetti",
      aciklama:
        "Kalıcı bir sağlayıcı hatası — bekleyerek düzelmez, sunucu tarafında model erişimi/anahtarı kontrol edilmeli.",
    };
  if (zarf.durum === 400 || zarf.durum === 422)
    return {
      baslik: "Soru işlenemedi",
      aciklama: `Soru boş olamaz ve en fazla ${ASK_MAX_LENGTH} karakter olabilir. Kısaltıp tekrar dene.`,
    };
  return {
    baslik: "Soru cevaplanamadı",
    aciklama:
      // Zarf mesajı backend'in kendi TR metni (iç detay sızdırmaz, api/errors.py);
      // tanınmayan durumda onu göstermek uydurmaktan dürüst
      zarf.mesaj || "Sunucu bu isteği karşılayamadı.",
  };
}

/* ── Parçalar ─────────────────────────────────────────────────────────────── */

function HataBloku({ hata }: { hata: unknown }) {
  const { baslik, aciklama } = hataMetni(hata);
  return (
    // Ev kalıbı (PresenceStrip · ScopePage/KararlarPaneli): panel içi hata =
    // severity-high tonlu blok. Nötr kart, hatayı normal içerik gibi gösterirdi.
    <div
      role="alert"
      className="rounded-lg border border-severity-high/40 bg-severity-high/10 p-4"
    >
      <p className="text-sm font-medium text-severity-high">
        <span aria-hidden className="mr-1.5">
          ▲
        </span>
        {baslik}
      </p>
      <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{aciklama}</p>
      <p className="mt-3 font-mono text-[11px] text-muted-foreground">
        Teknik ayrıntı: {teknikKunye(hata)}
      </p>
    </div>
  );
}

const CITE_RE = /\[cite:([^\]\s]+)\]/g;

/** Judge cevabı metin içine `[cite:T-58]` yerleştiriyor (engine/query.py
    _CITATION_RE + _validated_citations: placeholder'lar citations ile birebir
    eşleşmezse backend zaten hata veriyor). Onları okunur `[1]` numarasına
    çevirip ilgili alıntıya bağlıyoruz — ref bilinmiyorsa ham ref basılır. */
function CevapMetni({ answer, refSirasi }: { answer: string; refSirasi: Map<string, number> }) {
  const parcalar: ReactNode[] = [];
  let imlec = 0;
  for (const eslesme of answer.matchAll(CITE_RE)) {
    const bas = eslesme.index;
    if (bas > imlec) parcalar.push(answer.slice(imlec, bas));
    const ref = eslesme[1] ?? "";
    const sira = refSirasi.get(ref);
    parcalar.push(
      sira === undefined ? (
        <span key={`${ref}-${bas}`} className="font-mono text-xs text-muted-foreground">
          [{ref}]
        </span>
      ) : (
        <a
          key={`${ref}-${bas}`}
          href={`#alinti-${sira}`}
          title={`Alıntı ${sira}: ${ref}`}
          className="rounded bg-muted px-1 font-mono text-[11px] text-muted-foreground hover:text-foreground"
        >
          [{sira}]
        </a>
      ),
    );
    imlec = bas + eslesme[0].length;
  }
  if (imlec < answer.length) parcalar.push(answer.slice(imlec));
  return <p className="whitespace-pre-wrap text-sm leading-relaxed">{parcalar}</p>;
}

function AlintiSatiri({ alinti, sira }: { alinti: string | Citation; sira: number }) {
  // citations UNION: düz string de gelebilir (kontrat Ek), o hâlde yalnız ref var
  const duz = typeof alinti === "string";
  const ref = duz ? alinti : alinti.ref;
  const tur = duz ? null : alinti.type;
  const alintiMetni = duz ? null : alinti.quote;
  const url = duz ? null : alinti.url;
  const aralik = duz ? null : alinti.range;

  return (
    <li
      id={`alinti-${sira}`}
      className="rounded-lg border border-border bg-card px-4 py-3 target:border-foreground/25"
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">
          {sira}
        </span>
        {tur && (
          <span className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
            {TUR_ETIKET[tur]}
          </span>
        )}
        <span className="font-mono text-xs">{ref}</span>
        {aralik && (
          <span className="text-[11px] tabular-nums text-muted-foreground">
            satır {aralik.start}–{aralik.end}
          </span>
        )}
        {url && (
          <a
            href={url}
            target="_blank"
            rel="noreferrer"
            className="ml-auto text-xs text-primary hover:underline"
          >
            Kaynağı aç ↗
          </a>
        )}
      </div>
      {alintiMetni && (
        <blockquote className="mt-2 border-l-2 border-border pl-3 text-sm leading-relaxed text-muted-foreground">
          {alintiMetni}
        </blockquote>
      )}
    </li>
  );
}

function AramaFisi({ searched }: { searched: QueryResponse["searched"] }) {
  const dolu = searched.filter((s) => s.count > 0);
  if (dolu.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        Aranan kanonik kaynak yok — proje bağlamı henüz indekslenmemiş.
      </p>
    );
  }
  return (
    <p className="text-xs text-muted-foreground">
      Aranan kaynaklar:{" "}
      {dolu.map((s, i) => (
        <span key={s.type}>
          {i > 0 && " · "}
          <span className="tabular-nums">{s.count}</span> {TUR_ETIKET[s.type]}
        </span>
      ))}
    </p>
  );
}

function CevapBloku({ data }: { data: QueryResponse }) {
  const alintilar = data.citations;
  // ref → görünür alıntı numarası (Citation.n varsa ona saygı duy, yoksa sıra)
  const refSirasi = new Map<string, number>();
  alintilar.forEach((c, i) => {
    const ref = typeof c === "string" ? c : c.ref;
    if (!refSirasi.has(ref)) refSirasi.set(ref, typeof c === "string" ? i + 1 : (c.n ?? i + 1));
  });

  const bulunamadi = data.status === "not_found";

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-border bg-card p-4">
        {bulunamadi ? (
          // not_found HATA DEĞİL: "aradım, bulamadım" dürüst bir cevaptır
          <>
            <p className="text-sm font-medium">Bu soruya kanıtlı cevap bulunamadı</p>
            <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
              {data.answer}
            </p>
          </>
        ) : (
          <CevapMetni answer={data.answer} refSirasi={refSirasi} />
        )}

        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-border pt-3 text-[11px] text-muted-foreground">
          <span>{GUVEN_ETIKET[data.confidence]}</span>
          <span aria-hidden>·</span>
          <span>cevap anı: {zaman(data.as_of)}</span>
          <span aria-hidden>·</span>
          <span className="font-mono">commit {data.last_commit}</span>
          {data.window && (
            <>
              <span aria-hidden>·</span>
              <span>pencere: {data.window}</span>
            </>
          )}
        </div>
      </div>

      {alintilar.length > 0 ? (
        <div className="space-y-2">
          {/* ALL-CAPS yasak (D-34, TR İ/ı tuzağı) — hiyerarşi punto + ağırlık + renkle */}
          <h2 className="text-[11px] font-semibold tracking-wide text-muted-foreground">
            Kaynak alıntıları
          </h2>
          <ul className="space-y-2">
            {alintilar.map((c, i) => (
              <AlintiSatiri
                key={`${typeof c === "string" ? c : c.ref}-${i}`}
                alinti={c}
                sira={refSirasi.get(typeof c === "string" ? c : c.ref) ?? i + 1}
              />
            ))}
          </ul>
        </div>
      ) : (
        // Alıntısız cevap görünür biçimde işaretlenir (halüsinasyon algısına karşı)
        <p className="text-xs text-muted-foreground">
          Bu cevap hiçbir kanonik kaynağa bağlanmadı — kanıtsız olarak değerlendir.
        </p>
      )}

      {bulunamadi && data.nearest.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-[11px] font-semibold tracking-wide text-muted-foreground">
            En yakın kayıtlar
          </h2>
          <ul className="flex flex-wrap gap-1.5">
            {data.nearest.map((n) => (
              <li
                key={`${n.type}-${n.ref}`}
                className="rounded border border-border bg-card px-2 py-1 text-xs"
              >
                <span className="text-muted-foreground">{TUR_ETIKET[n.type]} </span>
                <span className="font-mono">{n.ref}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <AramaFisi searched={data.searched} />
    </div>
  );
}

/* ── Sayfa ────────────────────────────────────────────────────────────────── */

export default function AskPage() {
  // Taslak (kutudaki metin) ile SORULAN soru ayrı: her tuşta LLM'e gitmiyoruz.
  const [taslak, setTaslak] = useState("");
  const [soru, setSoru] = useState("");
  const { data, error, isLoading, isFetching, dataUpdatedAt } = useAsk(soru);

  const sor = (metin: string) => {
    const temiz = metin.trim();
    if (!temiz) return; // boş soruyla istek ATILMAZ (hook da enabled ile kapatıyor)
    setTaslak(metin);
    setSoru(temiz);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-base font-semibold">Projeye Sor</h1>
        {/* Bu sayfa poll'lanmıyor (tek-atış uç): gösterge ancak cevap gelince anlamlı */}
        {dataUpdatedAt > 0 && (
          <SonGuncelleme dataUpdatedAt={dataUpdatedAt} isFetching={isFetching} />
        )}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          sor(taslak);
        }}
        className="space-y-2"
      >
        <label htmlFor="ask-soru" className="sr-only">
          Projeye sorulacak soru
        </label>
        <div className="flex items-center gap-2">
          <input
            id="ask-soru"
            type="text"
            value={taslak}
            onChange={(e) => setTaslak(e.target.value)}
            maxLength={ASK_MAX_LENGTH}
            autoComplete="off"
            placeholder="Örn: Son 3 gün içinde ne değişti?"
            // focus:outline-none YOK: uygulamadaki hiçbir kontrol odak halkasını
            // bastırmıyor (Radar filtreleri · Graph hücreleri · nav) — tek istisna
            // olmak hem tutarsız hem klavye kullanıcısına karşı.
            className="min-w-0 flex-1 rounded-lg border border-border bg-card px-4 py-3 text-sm placeholder:text-muted-foreground focus:border-foreground/25"
          />
          <button
            type="submit"
            disabled={taslak.trim().length === 0}
            className="shrink-0 rounded-lg bg-primary px-4 py-3 text-sm font-medium text-primary-foreground disabled:cursor-not-allowed disabled:bg-muted disabled:text-muted-foreground"
          >
            Sor
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-muted-foreground">Örnek sorular:</span>
          {ORNEK_SORULAR.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => sor(s)}
              className="rounded px-2 py-1 text-xs text-muted-foreground hover:bg-muted/50"
            >
              {s}
            </button>
          ))}
          {taslak.length > ASK_MAX_LENGTH - 100 && (
            <span className="ml-auto text-xs tabular-nums text-muted-foreground">
              {taslak.length}/{ASK_MAX_LENGTH}
            </span>
          )}
        </div>
      </form>

      <section aria-live="polite" aria-busy={isLoading}>
        {soru === "" ? (
          // Henüz sorulmadı — bu "boş sonuç" değil, davetkâr başlangıç durumu
          <EmptyState
            title="Doğal dille sor, kaynak alıntılı cevap al"
            description="Soru; dondurulmuş kapsam, görev dosyaları, karar günlüğü ve PR geçmişi üzerinde aranır. Her cevap dayandığı alıntılarla birlikte gelir — kaynaksız cümle göstermiyoruz."
            items={[
              "Cevap kanonik .harness kayıtlarından üretilir",
              "Her iddia bir alıntıya bağlanır — bağlanamazsa cevap verilmez",
              "Tek atış: sayfa kendini yenilemez, kota boşa yakılmaz",
            ]}
            eta="Not: model kotası dolduğunda uç geçici olarak cevap veremez"
          />
        ) : isLoading ? (
          <YuklemeIskeleti label="Cevap hazırlanıyor" satir={2} />
        ) : error != null ? (
          // != null: openapi-fetch boş gövdeli non-ok cevapta error="" (falsy!)
          // verebilir; truthiness kontrolü hatayı sessizce yutardı
          <HataBloku hata={error} />
        ) : data === undefined ? (
          <p className="text-sm text-muted-foreground">Cevap bekleniyor…</p>
        ) : (
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">
              Soru: <span className="text-foreground">{soru}</span>
            </p>
            <CevapBloku data={data} />
          </div>
        )}
      </section>
    </div>
  );
}
