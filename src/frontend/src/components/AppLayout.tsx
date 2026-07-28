import { Link, NavLink, Outlet } from "react-router-dom";
import pkg from "../../package.json";
import { config } from "../lib/config";
import { useSaglik } from "../lib/useSaglik";
import { useSimdi } from "../lib/useSimdi";
import { gorunenAd, useAuth, useCikisYap } from "../lib/useAuth";
import { useRepolar } from "../lib/useRepoSecici";
import { useMcpConfig, useSaglayiciAyarlari } from "../lib/useSettings";
import {
  ActivityIcon,
  AskIcon,
  BoardIcon,
  GraphIcon,
  RadarIcon,
  ScopeIcon,
  SettingsIcon,
} from "./NavIcons";
import { ActorChip } from "./ui";

/* Bugünkü sabit demo etiketi (D-23) — anonim ziyaretçi/giriş yapılandırılmamış/
   girişli-ama-repo-verisi-henüz-yok durumlarının HEPSİNDE AYNEN korunur ("public
   demo BİREBİR aynı çalışmaya devam etmeli"). #79/T-79 öncesi tek değerdi,
   şimdi de öntanımlı/yedek değer. */
const DEMO_REPO_ETIKETI = "grup54/ensemble";

/** "Hangi repoya bakıyorum" göstergesi (#79/T-79) — AuthGostergesi'nin hemen
    yanında, AYNI sessizlik ilkesiyle: girişli değilse (ya da repo bilgisi
    henüz gelmediyse/hata verdiyse) sabit demo etiketine düşer, gürültü
    YAPMAZ. Girişliyse `/repolar`'a (repo seçici) giden bir link — kabul
    kriteri "seçiciye giden bir yol olmalı". */
function AktifRepoGostergesi() {
  const { kullanici } = useAuth();
  // Anonim ziyaretçi için BOŞUNA istek atma (useAuth.ts ilkesi) — /auth/repos
  // zaten oturumsuzken 401 döner, `enabled=false` bunu hiç denemez.
  const repolar = useRepolar(kullanici !== null);

  if (!kullanici) {
    return <span className="text-sm text-muted-foreground">{DEMO_REPO_ETIKETI}</span>;
  }

  const aktif =
    repolar.data?.tur === "basarili" ? (repolar.data.active ?? repolar.data.demo) : null;

  return (
    <Link
      to="/repolar"
      title="Repo seç / değiştir"
      className="text-sm text-muted-foreground hover:text-foreground hover:underline"
    >
      {aktif ?? DEMO_REPO_ETIKETI}
    </Link>
  );
}

/* Ters-L kabuk (Linear deseni): sol dar sidebar + üst ince bar.
   Sıra = demo anlatım sırası; Radar her zaman açılış sayfası.
   İkonlar #316/A2 — NavIcons.tsx (inline SVG, yeni bağımlılık yok). */

const NAV = [
  { to: "/radar", label: "Radar", Icon: RadarIcon },
  { to: "/board", label: "Board", Icon: BoardIcon },
  { to: "/scope", label: "Scope", Icon: ScopeIcon },
  { to: "/graph", label: "Graf", Icon: GraphIcon },
  { to: "/activity", label: "Activity", Icon: ActivityIcon },
  { to: "/ask", label: "Ask", Icon: AskIcon },
];

/** Ayarlar (/ayarlar, T-309) nav'da YALNIZ backend GERÇEKTEN 200 dönerse
    görünür — görev brifi §3: "Hosted'da bu sayfa GÖRÜNMESİN", bu dosyanın
    kendi ilkesi olan "çalışmayan sekme basmıyoruz"un aynısı. `config.mode`
    (Vite BUILD modu) DEĞİL, `GET /settings/saglayici`nin CANLI yanıtı kaynak
    (useSettings.ts dosya-başı yorumu — ikisi teorik olarak AYRIŞABİLİR).
    Yükleniyor/hata durumunda da GÖSTERİLMEZ (fail-closed: emin olmadan ölü
    link basma riski, emin olduktan sonra göstermekten daha ucuz).

    #332 — İKİNCİ KAYNAK: sayfada artık moddan bağımsız çalışan bir bölüm var
    (MCP bağlanma reçetesi, `GET /settings/mcp` hosted'da da 200). Link YALNIZ
    sağlayıcı ucuna bağlı kalsaydı hosted kullanıcı sayfayı hiç göremez, yeni
    bağlanma yolu ulaşılamaz kalırdı ("kodda var ama çalışmıyor"). Kural aynı:
    link, sayfada GERÇEKTEN gösterilecek bir şey olduğu KANITLANINCA basılır. */
function useAyarlarGorunurMu(): boolean {
  const ayarlar = useSaglayiciAyarlari();
  const mcp = useMcpConfig(true);
  return ayarlar.data?.tur === "basarili" || mcp.data?.tur === "basarili";
}

/* Başlıktaki KÜÇÜK auth göstergesi (#79, T-294 ile GitHub+email ikisini de
   kapsar) — demo giriş İSTEMEZ, bu yüzden bilinçli sessiz: yükleniyor / gerçek
   hata / hiçbir giriş yöntemi yapılandırılmamış (`enabled=false` VE
   `emailEnabled=false`) durumlarının HİÇBİRİNDE bir şey göstermez (görev
   brifi — "hiçbir şey gösterme, gürültü yapma"; yükleniyor/hata da aynı
   ilkeye tabi, bu ikincil bir gösterge — tam sayfa HataDurumu değil). */
function AuthGostergesi() {
  const { enabled, emailEnabled, kullanici, isLoading, error } = useAuth();
  const { cikisYap, yukleniyor } = useCikisYap();

  if (isLoading || error != null || (!enabled && !emailEnabled)) return null;

  if (kullanici) {
    return (
      <span className="flex items-center gap-2">
        <ActorChip handle={gorunenAd(kullanici)} type="human" />
        <button
          type="button"
          onClick={() => void cikisYap()}
          disabled={yukleniyor}
          className="text-xs text-muted-foreground hover:text-foreground disabled:cursor-not-allowed disabled:opacity-60"
        >
          {yukleniyor ? "Çıkış…" : "Çıkış"}
        </button>
      </span>
    );
  }

  // Girişli DEĞİL ama en az bir yöntem yapılandırılmış: KÜÇÜK, ikincil davet —
  // demo giriş istemediği için burada büyük bir CTA yok, yalnız bir link.
  return (
    <Link to="/login" className="text-xs text-muted-foreground hover:text-foreground">
      Giriş yap
    </Link>
  );
}

/** Topbar'daki canlılık nabzı (#316/A4) — eskiden burada `/health`'i
    ANIMSATAN ama hiçbir gerçek veriye bağlı olmayan sabit bir gri nokta
    vardı ("#20 canlandıracak" yorumu kalmıştı; #20 uzun zaman önce bitti,
    nokta hiç bağlanmadı). Artık AYNI `/health` sorgusunun (react-query
    cache'i topbar'daki mod rozetiyle PAYLAŞILIR, ikinci istek atılmaz)
    `dataUpdatedAt`'ından, gerçek "son başarılı yanıttan bu yana geçen süre"
    gösterir — sahte-canlılık yasak (D-34): hiç başarılı yanıt gelmediyse
    "CANLI" YAZILMAZ, dürüst bir ara/hata durumu basılır. */
function CanlilikNabzi() {
  const { error, dataUpdatedAt } = useSaglik();
  const simdi = useSimdi();

  if (dataUpdatedAt === 0) {
    const baglantiYok = error != null;
    return (
      <span
        className="flex items-center gap-1.5 text-xs text-muted-foreground"
        title={baglantiYok ? "Backend'e ulaşılamıyor" : "İlk /health yanıtı bekleniyor"}
      >
        <span
          aria-hidden
          className={`size-2 rounded-full ${baglantiYok ? "bg-severity-high" : "bg-status-backlog"}`}
        />
        {baglantiYok ? "Bağlantı yok" : "Bağlanıyor…"}
      </span>
    );
  }

  const gecenSn = Math.max(0, Math.round((simdi - dataUpdatedAt) / 1000));
  return (
    <span
      className="flex items-center gap-1.5 text-xs text-muted-foreground"
      title="Son başarılı /health yanıtından bu yana geçen süre"
    >
      <span aria-hidden className="size-2 animate-pulse rounded-full bg-status-done" />
      <span className="font-medium text-status-done">CANLI</span>
      <span className="tabular-nums">· {gecenSn} sn önce</span>
    </span>
  );
}

/** Kesişim logosu (#316/A1) — iki iç içe geçmiş halka ("ensemble/birliktelik"
    imgesi), eskiden turuncu dolu tek bir nokta vardı. Inline SVG, yeni
    bağımlılık yok (bu satırın hemen üstündeki yorum "Pencil'dan gelecek"
    diyordu, D-34 — artık geldi). */
function EnsembleLogo() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 20 20"
      fill="none"
      aria-hidden
      data-testid="ensemble-logo"
      className="shrink-0"
    >
      <circle cx="7.2" cy="10" r="6" stroke="currentColor" strokeWidth="1.6" className="text-primary" />
      <circle
        cx="12.8"
        cy="10"
        r="6"
        stroke="currentColor"
        strokeWidth="1.6"
        className="text-foreground"
      />
    </svg>
  );
}

export default function AppLayout() {
  const ayarlarGorunur = useAyarlarGorunurMu();
  const saglik = useSaglik();
  const nav = ayarlarGorunur
    ? [...NAV, { to: "/ayarlar", label: "Ayarlar", Icon: SettingsIcon }]
    : NAV;

  return (
    <div className="flex h-screen">
      <aside className="flex w-44 flex-col border-r border-border">
        <div className="flex items-center gap-2 px-4 py-4">
          <EnsembleLogo />
          <span className="text-sm font-semibold tracking-tight">Ensemble</span>
        </div>
        <nav className="flex-1 space-y-0.5 px-2">
          {nav.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end
              className={({ isActive }) =>
                `flex items-center gap-2 rounded px-2 py-1.5 text-sm ${
                  isActive
                    ? "bg-muted font-medium"
                    : "text-muted-foreground hover:bg-muted/50"
                }`
              }
            >
              <n.Icon className="size-4 shrink-0" />
              {n.label}
            </NavLink>
          ))}
        </nav>
        {/* Künye (#316/A3): local/hosted CANLI /health'ten (topbar rozetiyle
            AYNI sorgu, react-query cache paylaşır — ikinci istek atılmaz);
            sürüm gerçek kaynaktan (`package.json`, uydurma "v0.1" DEĞİL). */}
        <div className="border-t border-border px-4 py-3 text-[11px] text-muted-foreground">
          {saglik.data?.mode ?? config.mode} · v{pkg.version} · source-available
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-border px-4 py-2">
          <AktifRepoGostergesi />
          <div className="flex items-center gap-3">
            {config.mock && (
              // Sahte-canlılık yasak (D-34): mock modunda TÜM veriler örnektir —
              // tek şeride değil, globale işaret (yarım dürüstlük = dürüstsüzlük)
              <span className="rounded border border-status-in-review/40 bg-status-in-review/10 px-1.5 py-0.5 text-xs font-medium text-status-in-review">
                Örnek veri
              </span>
            )}
            {/* Mod rozeti CANLI `/health`'ten okunur — `config.mode` (Vite
                BUILD modu) DEĞİL. Masaüstü paketi de üretim derlemesi taşır
                ama YERELDE çalışır; build modundan türetilen rozet orada
                "hosted" derdi (bkz. lib/useSaglik.ts). Cevap gelene kadar
                derleme varsayılanı gösterilir — uydurma yok, yalnız
                elimizdeki en iyi bilgi. */}
            <span
              className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground"
              title={saglik.data?.mode ? "Sunucunun bildirdiği çalışma modu" : "Sunucudan mod bilgisi bekleniyor"}
            >
              {saglik.data?.mode ?? config.mode}
            </span>
            <CanlilikNabzi />
            <AuthGostergesi />
          </div>
        </header>
        {/* overflow-x-hidden (#316/H3): sayfa gövdesi hiçbir zaman yatay
            KAYMAMALI — geniş içerik (örn. 26 modüllük ısı matrisi) KENDİ
            `overflow-x-auto` kabında kayar (GraphPage/BoardPage/IsiMatrisi
            zaten böyle), burası yalnız savunma: bir sayfa yanlışlıkla
            taşırırsa main'in KENDİSİ yatay kaymasın, tek sorumlu iç kap kalsın. */}
        <main className="min-w-0 flex-1 overflow-x-hidden overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
