/* Onboarding sihirbazı (#340, §8.5) — üç giriş modu · sabit şema · AI taslağı ·
   kapasiteye göre sprint dağıtımı · İNSAN ONAYI (K6).

   Sayfanın taşıdığı üç kural (hepsi backend'de de uygulanır, burada GÖRÜNÜR olur):
   1. **K6:** onay kutusu işaretlenmeden "Yaz" düğmesi ETKİN OLMAZ ve istek
      atılmaz. Sunucu ayrıca 403 ile reddeder — iki katman, çünkü tek katman
      atlatılabilir (curl).
   2. **Uydurma yok:** eksik alanlar "eksik" rozetiyle görünür, AI'nın doldurduğu
      alanlar "AI varsayımı" rozetiyle. İkisi AYRI renk/etiket — kullanıcı neyi
      onayladığını bilmeli.
   3. **Sessiz düşüş yok:** sağlayıcı kotası biterse boş ekran değil, `degraded`
      bloğu basılır (neden + hangi aşama) ve LLM'siz modlar çalışmaya devam eder.

   Tasarım dili mevcut sayfalardan devralınır (Card/EmptyState/HataDurumu/
   YuklemeIskeleti, `components/ui.tsx`) — yeni bir dil icat edilmedi. */

import { useState } from "react";
import { Card, EmptyState, HataDurumu, YuklemeIskeleti } from "../components/ui";
import {
  BOS_BRIEF,
  type Brief,
  type Eksik,
  type Mod,
  type OnboardingDegraded,
  type Soru,
  type SprintPlani,
  type StoryTaslagi,
  type Uyari,
  type UygulaSonucu,
  briefUret,
  planUret,
  satirlaraBol,
  satirlariBirlestir,
  sorulariGetir,
  taslakUret,
  uygula,
  useOnboardingDurum,
} from "../lib/useOnboarding";

type Adim = "mod" | "girdi" | "brief" | "taslak" | "plan" | "onay";

const ADIMLAR: { id: Adim; etiket: string }[] = [
  { id: "mod", etiket: "Mod" },
  { id: "girdi", etiket: "Girdi" },
  { id: "brief", etiket: "Brief" },
  { id: "taslak", etiket: "Story" },
  { id: "plan", etiket: "Sprint" },
  { id: "onay", etiket: "Onay" },
];

const MOD_KARTLARI: { mod: Mod; baslik: string; aciklama: string; rozet: string }[] = [
  {
    mod: "anlat",
    baslik: "Anlat",
    aciklama:
      "Projeni serbest metinle anlat; yapıyı AI çıkarır. Tek bir LLM çağrısı yapılır.",
    rozet: "AI gerekir",
  },
  {
    mod: "soru_cevap",
    baslik: "Soru-cevap",
    aciklama:
      "Altı alanın her biri için tek bir soru. Yalnız boşluk kalırsa en çok iki tur daha sorulur.",
    rozet: "AI gerekmez",
  },
  {
    mod: "kendim",
    baslik: "Kendim girerim",
    aciklama: "Şemayı doğrudan doldur. Hiçbir model çağrılmaz.",
    rozet: "AI gerekmez",
  },
];

export default function OnboardingPage() {
  const durum = useOnboardingDurum();

  const [adim, setAdim] = useState<Adim>("mod");
  const [mod, setMod] = useState<Mod>("soru_cevap");
  const [brief, setBrief] = useState<Brief>(BOS_BRIEF);
  const [serbestMetin, setSerbestMetin] = useState("");
  const [cevaplar, setCevaplar] = useState<Record<string, string>>({});
  const [sorular, setSorular] = useState<Soru[]>([]);
  const [soruTuru, setSoruTuru] = useState(1);
  const [eksikler, setEksikler] = useState<Eksik[]>([]);
  const [uyarilar, setUyarilar] = useState<Uyari[]>([]);
  const [briefDegraded, setBriefDegraded] = useState<OnboardingDegraded | null>(null);
  const [taslak, setTaslak] = useState<StoryTaslagi | null>(null);
  const [taslakDegraded, setTaslakDegraded] = useState<OnboardingDegraded | null>(null);
  const [plan, setPlan] = useState<SprintPlani | null>(null);
  const [onaylandi, setOnaylandi] = useState(false);
  const [onaylayan, setOnaylayan] = useState("");
  const [sonuc, setSonuc] = useState<UygulaSonucu | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [mesgul, setMesgul] = useState(false);

  const d = durum.data;
  if (durum.isLoading || d === undefined) {
    return <YuklemeIskeleti label="Sihirbaz yükleniyor" satir={4} />;
  }
  if (d.tur !== "basarili") {
    return (
      <HataDurumu
        baslik="Sihirbaza ulaşılamıyor"
        aciklama="Backend cevap vermedi. Bağlantıyı ve VITE_API_BASE_URL'i kontrol et."
        hata={d.mesaj}
      />
    );
  }

  async function calistir<T>(is: () => Promise<T>, sonra: (v: T) => void) {
    setMesgul(true);
    setHata(null);
    try {
      sonra(await is());
    } finally {
      setMesgul(false);
    }
  }

  function modSec(secilen: Mod) {
    setMod(secilen);
    setBriefDegraded(null);
    if (secilen === "kendim") {
      setAdim("brief");
      return;
    }
    if (secilen === "anlat") {
      setAdim("girdi");
      return;
    }
    void calistir(
      () => sorulariGetir({ mod: secilen, tur: 1, brief }),
      (cevap) => {
        if (cevap.tur !== "basarili") {
          setHata(cevap.mesaj);
          return;
        }
        setSorular(cevap.sorular);
        setSoruTuru(1);
        setAdim("girdi");
      },
    );
  }

  function briefIste(varsayimlarla: boolean) {
    void calistir(
      () =>
        briefUret({
          mod,
          serbest_metin: serbestMetin,
          cevaplar,
          brief,
          varsayimlarla_doldur: varsayimlarla,
        }),
      (cevap) => {
        if (cevap.tur !== "basarili") {
          setHata(cevap.mesaj);
          return;
        }
        setBrief(cevap.brief);
        setEksikler(cevap.eksikler);
        setUyarilar(cevap.uyarilar);
        setBriefDegraded(cevap.degraded ?? null);
        setCevaplar({});
        setAdim("brief");
      },
    );
  }

  function bosluklariSor() {
    const sonrakiTur = soruTuru + 1;
    void calistir(
      () => sorulariGetir({ mod, tur: sonrakiTur, brief }),
      (cevap) => {
        if (cevap.tur !== "basarili") {
          setHata(cevap.mesaj);
          return;
        }
        setSorular(cevap.sorular);
        setSoruTuru(cevap.soruTuru);
        // Boşluk turu soru-cevap mekaniğiyle işler; "anlat" modunda da aynı
        // form kullanılır (mod karışabilir — §8.5: "karışık olabilir").
        setMod("soru_cevap");
        setAdim("girdi");
      },
    );
  }

  function taslakIste() {
    void calistir(
      () => taslakUret(brief),
      (cevap) => {
        if (cevap.tur !== "basarili") {
          setHata(cevap.mesaj);
          return;
        }
        setTaslak(cevap.taslak);
        setTaslakDegraded(cevap.degraded ?? null);
        setAdim("taslak");
      },
    );
  }

  function planIste() {
    const ekip = brief.kisitlar.ekip_buyuklugu;
    const sprint = brief.kisitlar.sprint_sayisi;
    if (!ekip || !sprint || !taslak) {
      setHata(
        "Sprint dağıtımı için ekip büyüklüğü ve sprint sayısı gerekir — Kısıtlar alanını doldur.",
      );
      return;
    }
    void calistir(
      () =>
        planUret({
          storyler: taslak.storyler,
          kapasite: { ekip_buyuklugu: ekip, sprint_sayisi: sprint },
        }),
      (cevap) => {
        if (cevap.tur !== "basarili") {
          setHata(cevap.mesaj);
          return;
        }
        setPlan(cevap.plan);
        setAdim("plan");
      },
    );
  }

  function yaz() {
    if (!onaylandi || !taslak) return; // K6: istemci katmanı (sunucu da 403 verir)
    void calistir(
      () =>
        uygula({
          onay: { onaylandi: true, onaylayan: onaylayan.trim() || "bilinmiyor" },
          brief,
          taslak,
          plan,
        }),
      setSonuc,
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-base font-semibold">Onboarding sihirbazı</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Projeni kaybolmadan anlat; sihirbaz sabit bir şemayı doldurur, story
            taslağı ve sprint dağıtımı önerir. <strong>Diske ancak sen onaylayınca yazar.</strong>
          </p>
        </div>
        <AdimSeridi aktif={adim} />
      </div>

      <KurulumSeridi
        saglayici={d.saglayici}
        aiVar={d.ai_kullanilabilir}
        yazmaMumkun={d.yazma_mumkun}
        yazmaEngeli={d.yazma_engeli ?? null}
        kok={d.yazma_kok}
        harnessVar={d.harness_var}
      />

      {hata !== null && (
        <p
          role="alert"
          className="rounded-lg border border-severity-high/40 bg-severity-high/10 px-3 py-2 text-xs text-severity-high"
        >
          {hata}
        </p>
      )}

      {mesgul && <YuklemeIskeleti label="Sihirbaz çalışıyor" satir={2} />}

      {!mesgul && adim === "mod" && <ModSecimi onSec={modSec} aiVar={d.ai_kullanilabilir} />}

      {!mesgul && adim === "girdi" && (
        <GirdiAdimi
          mod={mod}
          tur={soruTuru}
          sorular={sorular}
          cevaplar={cevaplar}
          serbestMetin={serbestMetin}
          onSerbestMetin={setSerbestMetin}
          onCevap={(alan, deger) => setCevaplar((o) => ({ ...o, [alan]: deger }))}
          onDevam={() => briefIste(false)}
          onBununlaDevam={() => briefIste(true)}
          onGeri={() => setAdim("mod")}
        />
      )}

      {!mesgul && adim === "brief" && (
        <BriefAdimi
          brief={brief}
          eksikler={eksikler}
          uyarilar={uyarilar}
          degraded={briefDegraded}
          turBitti={soruTuru >= d.maks_bosluk_turu}
          onDegistir={setBrief}
          onDogrula={() => briefIste(false)}
          onBosluklariSor={bosluklariSor}
          onBununlaDevam={() => briefIste(true)}
          onIleri={taslakIste}
        />
      )}

      {!mesgul && adim === "taslak" && taslak && (
        <TaslakAdimi
          taslak={taslak}
          degraded={taslakDegraded}
          onGeri={() => setAdim("brief")}
          onPlan={planIste}
          onOnay={() => setAdim("onay")}
        />
      )}

      {!mesgul && adim === "plan" && plan && (
        <PlanAdimi plan={plan} onGeri={() => setAdim("taslak")} onOnay={() => setAdim("onay")} />
      )}

      {!mesgul && adim === "onay" && taslak && (
        <OnayAdimi
          brief={brief}
          taslak={taslak}
          plan={plan}
          yazmaMumkun={d.yazma_mumkun}
          kok={d.yazma_kok}
          onaylandi={onaylandi}
          onaylayan={onaylayan}
          sonuc={sonuc}
          onOnayDegis={setOnaylandi}
          onAdDegis={setOnaylayan}
          onYaz={yaz}
          onGeri={() => setAdim("taslak")}
        />
      )}
    </div>
  );
}

/* ── Ortak parçalar ───────────────────────────────────────────────────── */

function AdimSeridi({ aktif }: { aktif: Adim }) {
  const indeks = ADIMLAR.findIndex((a) => a.id === aktif);
  return (
    <ol className="flex flex-wrap items-center gap-1 text-xs" aria-label="Sihirbaz adımları">
      {ADIMLAR.map((a, i) => (
        <li key={a.id} className="flex items-center gap-1">
          <span
            aria-current={a.id === aktif ? "step" : undefined}
            className={`rounded px-1.5 py-0.5 ${
              i === indeks
                ? "bg-primary/15 font-medium text-primary"
                : i < indeks
                  ? "text-status-done"
                  : "text-muted-foreground"
            }`}
          >
            {i + 1}. {a.etiket}
          </span>
          {i < ADIMLAR.length - 1 && (
            <span aria-hidden className="text-muted-foreground">
              ›
            </span>
          )}
        </li>
      ))}
    </ol>
  );
}

/** Kurulum gerçeği — TIKLAMADAN ÖNCE söylenir (D-34: iş yapmayan buton basmıyoruz). */
function KurulumSeridi({
  saglayici,
  aiVar,
  yazmaMumkun,
  yazmaEngeli,
  kok,
  harnessVar,
}: {
  saglayici: string;
  aiVar: boolean;
  yazmaMumkun: boolean;
  yazmaEngeli: string | null;
  kok: string;
  harnessVar: boolean;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-border bg-card px-4 py-2.5 text-xs">
      <span className="inline-flex items-center gap-1.5">
        <span aria-hidden>{aiVar ? "◆" : "○"}</span>
        <span className="text-muted-foreground">AI sağlayıcı:</span>
        <span className="font-medium">{aiVar ? saglayici : "yok"}</span>
      </span>
      {!aiVar && (
        <span className="text-muted-foreground">
          “Anlat” modu sağlayıcı ister; “Soru-cevap” ve “Kendim girerim” çalışmaya devam eder.
        </span>
      )}
      <span className="inline-flex items-center gap-1.5">
        <span aria-hidden>{yazmaMumkun ? "◆" : "○"}</span>
        <span className="text-muted-foreground">Yazma:</span>
        <span className="font-medium">{yazmaMumkun ? kok : "kapalı"}</span>
      </span>
      {/* "Buton kapalı" demek yetmez — NEDEN kapalı olduğu sunucudan gelir
          ve AYNEN basılır (sessiz düşüş yasağı). */}
      {!yazmaMumkun && yazmaEngeli !== null && (
        <span className="text-muted-foreground">{yazmaEngeli}</span>
      )}
      {yazmaMumkun && harnessVar && (
        <span className="text-muted-foreground">
          Bu repoda <code>.harness/</code> zaten var — var olan dosyalar EZİLMEZ.
        </span>
      )}
    </div>
  );
}

function DegradedBlogu({ degraded }: { degraded: OnboardingDegraded }) {
  return (
    <div
      role="alert"
      data-testid="onboarding-degraded"
      className="rounded-lg border border-status-in-review/40 bg-status-in-review/10 px-3 py-2 text-xs text-status-in-review"
    >
      <strong>
        {degraded.asama === "brief" ? "Brief" : "Story"} taslağı üretilemedi.
      </strong>{" "}
      Sağlayıcı: {degraded.saglayici}. {degraded.neden} — bu ekranda uydurma taslak
      göstermiyoruz; elle doldurmaya devam edebilirsin.
    </div>
  );
}

function Dugme({
  children,
  onClick,
  birincil = false,
  disabled = false,
  type = "button",
}: {
  children: React.ReactNode;
  onClick?: () => void;
  birincil?: boolean;
  disabled?: boolean;
  type?: "button" | "submit";
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`rounded px-3 py-1.5 text-sm disabled:cursor-not-allowed disabled:opacity-50 ${
        birincil
          ? "bg-primary text-primary-foreground hover:opacity-90"
          : "border border-border text-muted-foreground hover:bg-muted/50"
      }`}
    >
      {children}
    </button>
  );
}

/* ── Adım 1: mod seçimi ───────────────────────────────────────────────── */

function ModSecimi({ onSec, aiVar }: { onSec: (m: Mod) => void; aiVar: boolean }) {
  return (
    <div className="grid gap-3 md:grid-cols-3">
      {MOD_KARTLARI.map((k) => {
        const kapali = k.mod === "anlat" && !aiVar;
        return (
          <Card key={k.mod} className="flex flex-col justify-between gap-3">
            <div>
              <div className="flex items-center justify-between gap-2">
                <h2 className="text-sm font-semibold">{k.baslik}</h2>
                <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
                  {k.rozet}
                </span>
              </div>
              <p className="mt-2 text-xs text-muted-foreground">{k.aciklama}</p>
            </div>
            <Dugme birincil onClick={() => onSec(k.mod)} disabled={kapali}>
              {kapali ? "Sağlayıcı yok" : "Bu modla başla"}
            </Dugme>
          </Card>
        );
      })}
    </div>
  );
}

/* ── Adım 2: girdi ────────────────────────────────────────────────────── */

function GirdiAdimi({
  mod,
  tur,
  sorular,
  cevaplar,
  serbestMetin,
  onSerbestMetin,
  onCevap,
  onDevam,
  onBununlaDevam,
  onGeri,
}: {
  mod: Mod;
  tur: number;
  sorular: Soru[];
  cevaplar: Record<string, string>;
  serbestMetin: string;
  onSerbestMetin: (v: string) => void;
  onCevap: (alan: string, deger: string) => void;
  onDevam: () => void;
  onBununlaDevam: () => void;
  onGeri: () => void;
}) {
  if (mod === "anlat") {
    return (
      <Card className="space-y-3">
        <h2 className="text-sm font-semibold">Projeni anlat</h2>
        <p className="text-xs text-muted-foreground">
          Ne yapıyorsun, kime, hangi problemi çözüyor? Ekip, süre, teknoloji ve
          yapmayacakların da geçsin. Metinde olmayanı sihirbaz uydurmaz — eksik
          kalanları işaretler.
        </p>
        <textarea
          aria-label="Serbest metin"
          value={serbestMetin}
          onChange={(e) => onSerbestMetin(e.target.value)}
          rows={10}
          className="w-full rounded border border-border bg-card p-3 text-sm"
          placeholder="Örn: Yazılım ekipleri için bir koordinasyon aracı yapıyoruz…"
        />
        <div className="flex flex-wrap gap-2">
          <Dugme birincil onClick={onDevam} disabled={serbestMetin.trim().length === 0}>
            Yapıyı çıkar
          </Dugme>
          <Dugme onClick={onBununlaDevam} disabled={serbestMetin.trim().length === 0}>
            Bununla devam et (boşlukları AI varsaysın)
          </Dugme>
          <Dugme onClick={onGeri}>Geri</Dugme>
        </div>
      </Card>
    );
  }

  return (
    <Card className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">
          {tur === 1 ? "Altı soru, altı alan" : `Boşluk turu ${tur - 1}`}
        </h2>
        <span className="text-xs text-muted-foreground">
          {tur === 1
            ? "Her alan için tek soru"
            : "Yalnız eksik kalan alanlar soruluyor"}
        </span>
      </div>
      {sorular.length === 0 && (
        <p className="text-xs text-muted-foreground">
          Sorulacak bir şey kalmadı — soru turu hakkı bitti. Alanları elle
          düzenleyebilir ya da “bununla devam et” diyebilirsin.
        </p>
      )}
      {sorular.map((s) => (
        <div key={s.alan} className="space-y-1">
          <label htmlFor={`soru-${s.alan}`} className="block text-sm font-medium">
            {s.metin}
          </label>
          <p className="text-xs text-muted-foreground">{s.ipucu}</p>
          {s.coklu ? (
            <textarea
              id={`soru-${s.alan}`}
              rows={4}
              value={cevaplar[s.alan] ?? ""}
              onChange={(e) => onCevap(s.alan, e.target.value)}
              className="w-full rounded border border-border bg-card p-2 text-sm"
            />
          ) : (
            <input
              id={`soru-${s.alan}`}
              value={cevaplar[s.alan] ?? ""}
              onChange={(e) => onCevap(s.alan, e.target.value)}
              className="w-full rounded border border-border bg-card p-2 text-sm"
            />
          )}
        </div>
      ))}
      <div className="flex flex-wrap gap-2">
        <Dugme birincil onClick={onDevam}>
          Devam
        </Dugme>
        <Dugme onClick={onBununlaDevam}>Bununla devam et (boşlukları AI varsaysın)</Dugme>
        <Dugme onClick={onGeri}>Geri</Dugme>
      </div>
    </Card>
  );
}

/* ── Adım 3: brief ────────────────────────────────────────────────────── */

function MetinAlani({
  etiket,
  deger,
  onDegis,
  cokSatir = false,
  eksik,
  varsayim,
}: {
  etiket: string;
  deger: string;
  onDegis: (v: string) => void;
  cokSatir?: boolean;
  eksik?: Eksik;
  varsayim?: boolean;
}) {
  return (
    <div className="space-y-1">
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor={`alan-${etiket}`} className="text-sm font-medium">
          {etiket}
        </label>
        {eksik && (
          <span className="rounded bg-severity-high/15 px-1.5 py-0.5 text-[11px] font-medium text-severity-high">
            {eksik.neden === "bos" ? "eksik" : "yetersiz"}
          </span>
        )}
        {varsayim && (
          <span className="rounded bg-status-in-review/15 px-1.5 py-0.5 text-[11px] font-medium text-status-in-review">
            AI varsayımı
          </span>
        )}
      </div>
      {eksik && <p className="text-xs text-muted-foreground">{eksik.aciklama}</p>}
      {cokSatir ? (
        <textarea
          id={`alan-${etiket}`}
          rows={4}
          value={deger}
          onChange={(e) => onDegis(e.target.value)}
          className="w-full rounded border border-border bg-card p-2 text-sm"
        />
      ) : (
        <input
          id={`alan-${etiket}`}
          value={deger}
          onChange={(e) => onDegis(e.target.value)}
          className="w-full rounded border border-border bg-card p-2 text-sm"
        />
      )}
    </div>
  );
}

function BriefAdimi({
  brief,
  eksikler,
  uyarilar,
  degraded,
  turBitti,
  onDegistir,
  onDogrula,
  onBosluklariSor,
  onBununlaDevam,
  onIleri,
}: {
  brief: Brief;
  eksikler: Eksik[];
  uyarilar: Uyari[];
  degraded: OnboardingDegraded | null;
  turBitti: boolean;
  onDegistir: (b: Brief) => void;
  onDogrula: () => void;
  onBosluklariSor: () => void;
  onBununlaDevam: () => void;
  onIleri: () => void;
}) {
  const eksikHarita = new Map(eksikler.map((e) => [e.alan, e]));
  const varsayimAlanlari = new Set(brief.varsayimlar.map((v) => v.alan));

  return (
    <div className="space-y-4">
      {degraded && <DegradedBlogu degraded={degraded} />}

      <Card className="space-y-4">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold">Sabit şema (§8.5)</h2>
          <span className="text-xs text-muted-foreground">
            Her alan düzenlenebilir — bu bir taslaktır.
          </span>
        </div>

        <MetinAlani
          etiket="Ürün tek cümle"
          deger={brief.urun_tek_cumle}
          onDegis={(v) => onDegistir({ ...brief, urun_tek_cumle: v })}
          eksik={eksikHarita.get("urun_tek_cumle")}
          varsayim={varsayimAlanlari.has("urun_tek_cumle")}
        />
        <MetinAlani
          etiket="Hedef kullanıcılar"
          cokSatir
          deger={satirlariBirlestir(brief.hedef_kullanicilar)}
          onDegis={(v) => onDegistir({ ...brief, hedef_kullanicilar: satirlaraBol(v) })}
          eksik={eksikHarita.get("hedef_kullanicilar")}
          varsayim={varsayimAlanlari.has("hedef_kullanicilar")}
        />
        <MetinAlani
          etiket="Çekirdek özellikler"
          cokSatir
          deger={satirlariBirlestir(brief.cekirdek_ozellikler)}
          onDegis={(v) => onDegistir({ ...brief, cekirdek_ozellikler: satirlaraBol(v) })}
          eksik={eksikHarita.get("cekirdek_ozellikler")}
          varsayim={varsayimAlanlari.has("cekirdek_ozellikler")}
        />
        <MetinAlani
          etiket="Kapsam dışı"
          cokSatir
          deger={satirlariBirlestir(brief.kapsam_disi)}
          onDegis={(v) => onDegistir({ ...brief, kapsam_disi: satirlaraBol(v) })}
          eksik={eksikHarita.get("kapsam_disi")}
          varsayim={varsayimAlanlari.has("kapsam_disi")}
        />

        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium">Kısıtlar</span>
            {eksikHarita.get("kisitlar") && (
              <span className="rounded bg-severity-high/15 px-1.5 py-0.5 text-[11px] font-medium text-severity-high">
                {eksikHarita.get("kisitlar")!.neden === "bos" ? "eksik" : "yetersiz"}
              </span>
            )}
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="text-xs text-muted-foreground">
              Ekip büyüklüğü
              <input
                type="number"
                min={1}
                value={brief.kisitlar.ekip_buyuklugu ?? ""}
                onChange={(e) =>
                  onDegistir({
                    ...brief,
                    kisitlar: {
                      ...brief.kisitlar,
                      ekip_buyuklugu: e.target.value === "" ? null : Number(e.target.value),
                    },
                  })
                }
                className="mt-1 w-full rounded border border-border bg-card p-2 text-sm text-foreground"
              />
            </label>
            <label className="text-xs text-muted-foreground">
              Sprint sayısı
              <input
                type="number"
                min={1}
                value={brief.kisitlar.sprint_sayisi ?? ""}
                onChange={(e) =>
                  onDegistir({
                    ...brief,
                    kisitlar: {
                      ...brief.kisitlar,
                      sprint_sayisi: e.target.value === "" ? null : Number(e.target.value),
                    },
                  })
                }
                className="mt-1 w-full rounded border border-border bg-card p-2 text-sm text-foreground"
              />
            </label>
            <label className="text-xs text-muted-foreground sm:col-span-2">
              Teknolojiler / entegrasyonlar (her satıra bir madde)
              <textarea
                rows={3}
                value={satirlariBirlestir(brief.kisitlar.teknolojiler)}
                onChange={(e) =>
                  onDegistir({
                    ...brief,
                    kisitlar: { ...brief.kisitlar, teknolojiler: satirlaraBol(e.target.value) },
                  })
                }
                className="mt-1 w-full rounded border border-border bg-card p-2 text-sm text-foreground"
              />
            </label>
          </div>
        </div>

        <MetinAlani
          etiket="Başarı / demo hedefi"
          deger={brief.basari_hedefi}
          onDegis={(v) => onDegistir({ ...brief, basari_hedefi: v })}
          eksik={eksikHarita.get("basari_hedefi")}
          varsayim={varsayimAlanlari.has("basari_hedefi")}
        />
      </Card>

      {brief.varsayimlar.length > 0 && (
        <Card className="space-y-2">
          <h3 className="text-sm font-semibold">AI varsayımları — sen doğrulamalısın</h3>
          <ul className="space-y-1 text-xs text-muted-foreground">
            {brief.varsayimlar.map((v) => (
              <li key={`${v.alan}-${v.deger_ozeti}`}>
                <span className="font-medium text-foreground">{v.alan}</span>: {v.deger_ozeti}{" "}
                <em>({v.gerekce})</em>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {uyarilar.length > 0 && (
        <ul className="space-y-1 text-xs text-muted-foreground">
          {uyarilar.map((u) => (
            <li key={u.alan}>⚠ {u.aciklama}</li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap gap-2">
        <Dugme onClick={onDogrula}>Alanları yeniden doğrula</Dugme>
        {eksikler.length > 0 && !turBitti && (
          <Dugme onClick={onBosluklariSor}>Eksikleri sor ({eksikler.length})</Dugme>
        )}
        {eksikler.length > 0 && (
          <Dugme onClick={onBununlaDevam}>Bununla devam et (AI varsaysın)</Dugme>
        )}
        <Dugme birincil onClick={onIleri}>
          Story taslağını üret
        </Dugme>
      </div>
    </div>
  );
}

/* ── Adım 4: story taslağı ────────────────────────────────────────────── */

function TaslakAdimi({
  taslak,
  degraded,
  onGeri,
  onPlan,
  onOnay,
}: {
  taslak: StoryTaslagi;
  degraded: OnboardingDegraded | null;
  onGeri: () => void;
  onPlan: () => void;
  onOnay: () => void;
}) {
  return (
    <div className="space-y-4">
      {degraded && <DegradedBlogu degraded={degraded} />}

      {taslak.storyler.length === 0 ? (
        <EmptyState
          title="Story taslağı yok"
          description="Sağlayıcı taslak üretemedi. Uydurma story göstermiyoruz — yukarıdaki nedeni okuyup tekrar deneyebilir ya da alanları elle doldurup devam edebilirsin."
          eta="Kaynak: POST /onboarding/taslak"
        />
      ) : (
        <div className="space-y-3">
          {taslak.epicler.map((epic) => (
            <Card key={epic.id} className="space-y-2">
              <div className="flex items-center gap-2">
                <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] font-medium">
                  {epic.id}
                </span>
                <h3 className="text-sm font-semibold">{epic.baslik}</h3>
              </div>
              {epic.aciklama && (
                <p className="text-xs text-muted-foreground">{epic.aciklama}</p>
              )}
              <ul className="space-y-2">
                {taslak.storyler
                  .filter((s) => s.epic_id === epic.id)
                  .map((s) => (
                    <li key={s.id} className="rounded border border-border p-2">
                      <div className="flex flex-wrap items-center gap-2 text-xs">
                        <span className="font-medium">{s.id}</span>
                        <span className="rounded bg-muted px-1.5 py-0.5 tabular-nums">
                          {s.puan} puan
                        </span>
                        <span className="text-muted-foreground">öncelik {s.oncelik}</span>
                      </div>
                      <p className="mt-1 text-sm">
                        Bir {s.rol} olarak {s.istek} istiyorum, böylece {s.fayda}.
                      </p>
                      {s.kabul_kriterleri.length > 0 && (
                        <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
                          {s.kabul_kriterleri.map((k) => (
                            <li key={k}>☐ {k}</li>
                          ))}
                        </ul>
                      )}
                    </li>
                  ))}
              </ul>
            </Card>
          ))}
        </div>
      )}

      {taslak.dusenler.length > 0 && (
        <Card className="space-y-1">
          <h3 className="text-sm font-semibold">Taslakta düzeltilenler</h3>
          <p className="text-xs text-muted-foreground">
            Sessiz temizlik yok — modelin çıktısında düzeltilen/atılan her şey burada.
          </p>
          <ul className="space-y-0.5 text-xs text-muted-foreground">
            {taslak.dusenler.map((dd, i) => (
              <li key={`${dd.id}-${i}`}>
                <span className="font-medium text-foreground">{dd.id}</span>: {dd.neden}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <div className="flex flex-wrap gap-2">
        <Dugme onClick={onGeri}>Geri</Dugme>
        <Dugme birincil onClick={onPlan} disabled={taslak.storyler.length === 0}>
          Sprint dağıtımını öner
        </Dugme>
        <Dugme onClick={onOnay} disabled={taslak.storyler.length === 0}>
          Onaya geç (plansız)
        </Dugme>
      </div>
    </div>
  );
}

/* ── Adım 5: sprint dağıtımı ──────────────────────────────────────────── */

function PlanAdimi({
  plan,
  onGeri,
  onOnay,
}: {
  plan: SprintPlani;
  onGeri: () => void;
  onOnay: () => void;
}) {
  return (
    <div className="space-y-4">
      <Card className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold">Kapasiteye göre sprint dağıtımı</h2>
          <span className="text-xs text-muted-foreground">
            Toplam {plan.toplam_puan} puan · deterministik hesap (model değil)
          </span>
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          {plan.dilimler.map((dilim) => {
            const doluluk = dilim.butce > 0 ? Math.round((dilim.yuk / dilim.butce) * 100) : 0;
            return (
              <div key={dilim.sprint} className="rounded border border-border p-3">
                <div className="flex items-center justify-between text-sm font-medium">
                  <span>Sprint {dilim.sprint}</span>
                  <span className="tabular-nums text-muted-foreground">
                    {dilim.yuk}/{dilim.butce}
                  </span>
                </div>
                <span className="mt-2 block h-1.5 w-full overflow-hidden rounded-full bg-muted">
                  <span
                    aria-hidden
                    className={`block h-full rounded-full ${
                      doluluk > 100 ? "bg-severity-high" : "bg-status-done"
                    }`}
                    style={{ width: `${Math.min(doluluk, 100)}%` }}
                  />
                </span>
                <ul className="mt-2 space-y-0.5 text-xs text-muted-foreground">
                  {dilim.story_idler.map((sid) => (
                    <li key={sid}>{sid}</li>
                  ))}
                  {dilim.story_idler.length === 0 && <li>(boş)</li>}
                </ul>
              </div>
            );
          })}
        </div>
      </Card>

      {plan.uyarilar.length > 0 && (
        <Card className="space-y-1">
          <h3 className="text-sm font-semibold">Uyarılar</h3>
          <ul className="space-y-0.5 text-xs text-muted-foreground">
            {plan.uyarilar.map((u) => (
              <li key={u}>⚠ {u}</li>
            ))}
          </ul>
        </Card>
      )}

      <div className="flex flex-wrap gap-2">
        <Dugme onClick={onGeri}>Geri</Dugme>
        <Dugme birincil onClick={onOnay}>
          Onaya geç
        </Dugme>
      </div>
    </div>
  );
}

/* ── Adım 6: onay (K6) ────────────────────────────────────────────────── */

function OnayAdimi({
  brief,
  taslak,
  plan,
  yazmaMumkun,
  kok,
  onaylandi,
  onaylayan,
  sonuc,
  onOnayDegis,
  onAdDegis,
  onYaz,
  onGeri,
}: {
  brief: Brief;
  taslak: StoryTaslagi;
  plan: SprintPlani | null;
  yazmaMumkun: boolean;
  kok: string;
  onaylandi: boolean;
  onaylayan: string;
  sonuc: UygulaSonucu | null;
  onOnayDegis: (v: boolean) => void;
  onAdDegis: (v: string) => void;
  onYaz: () => void;
  onGeri: () => void;
}) {
  const sprintSayisi = plan?.dilimler.length ?? 1;

  if (sonuc?.tur === "basarili") {
    return (
      <Card className="space-y-2">
        <h2 className="text-sm font-semibold text-status-done">Yazıldı</h2>
        <p className="text-xs text-muted-foreground">
          Kök: <code>{sonuc.kok}</code>. Dosyalar birer TASLAK — git'e commit etmen
          onay/dondurma sayılır.
        </p>
        <ul className="space-y-0.5 text-xs text-muted-foreground">
          {sonuc.yazilan.map((y) => (
            <li key={y}>{y}</li>
          ))}
        </ul>
        {/* SON ADIM — ölçüldü (#340 duman testi): dosyalar diskte ama Board
            bir DB PROJEKSİYONU, `.harness/`'i canlı okumaz. Bunu söylemezsek
            kullanıcı "yazdı ama hiçbir şey olmadı" görür. Doğrulandı: rebuild
            sonrası üç görev de Board'da `backlog` sütununda çıkıyor. */}
        <p className="rounded border border-border bg-muted/40 px-2 py-1.5 text-xs text-muted-foreground">
          Board bir projeksiyondur, <code>.harness/</code>'i canlı okumaz —
          kartların görünmesi için <code>make rebuild</code> çalıştır.
        </p>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Card className="space-y-2">
        <h2 className="text-sm font-semibold">Ne yazılacak</h2>
        <ul className="space-y-0.5 text-xs text-muted-foreground">
          <li>
            <code>.harness/scope/sprint-N.md</code> — {sprintSayisi} kapsam belgesi
            (hedefler = yerleşen story'ler, kapsam dışı = senin listen)
          </li>
          <li>
            <code>.harness/tasks/T-*.md</code> — {taslak.storyler.length} görev dosyası
            (board'ın kanonik kaydı)
          </li>
          {brief.varsayimlar.length > 0 && (
            <li>
              {brief.varsayimlar.length} AI varsayımı kapsam belgesine{" "}
              <strong>işaretli olarak</strong> yazılır
            </li>
          )}
        </ul>
        {!yazmaMumkun && (
          <p className="rounded border border-status-in-review/40 bg-status-in-review/10 px-2 py-1.5 text-xs text-status-in-review">
            Bu kurulumda yazma adımı yok (hosted). Taslağı burada görüp
            düzenleyebilirsin; diske yazmak için Ensemble'ı kendi makinende
            (local) çalıştır.
          </p>
        )}
        {yazmaMumkun && (
          <p className="text-xs text-muted-foreground">
            Hedef kök: <code>{kok}</code>
          </p>
        )}
      </Card>

      <Card className="space-y-3">
        <h2 className="text-sm font-semibold">İnsan onayı (K6)</h2>
        <p className="text-xs text-muted-foreground">
          AI taslaklar, <strong>insan onaylar</strong>. Bu kutu işaretlenmeden hiçbir
          dosya yazılmaz — sunucu da onaysız isteği reddeder.
        </p>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={onaylandi}
            onChange={(e) => onOnayDegis(e.target.checked)}
          />
          Taslağı okudum, onaylıyorum
        </label>
        <label className="block text-xs text-muted-foreground">
          Onaylayan (git handle)
          <input
            value={onaylayan}
            onChange={(e) => onAdDegis(e.target.value)}
            placeholder="ör. fatiherencetin"
            className="mt-1 w-full rounded border border-border bg-card p-2 text-sm text-foreground"
          />
        </label>

        {sonuc && (
          <p
            role="alert"
            className="rounded border border-severity-high/40 bg-severity-high/10 px-2 py-1.5 text-xs text-severity-high"
          >
            {sonuc.mesaj}
          </p>
        )}

        <div className="flex flex-wrap gap-2">
          <Dugme onClick={onGeri}>Geri</Dugme>
          <Dugme birincil onClick={onYaz} disabled={!onaylandi || !yazmaMumkun}>
            .harness/ dizinine yaz
          </Dugme>
        </div>
      </Card>
    </div>
  );
}
