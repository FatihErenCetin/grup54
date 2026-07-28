import { Link, NavLink, Outlet } from "react-router-dom";
import { config } from "../lib/config";
import { gorunenAd, useAuth, useCikisYap } from "../lib/useAuth";
import { useRepolar } from "../lib/useRepoSecici";
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
   Sıra = demo anlatım sırası; Radar her zaman açılış sayfası. */

const NAV = [
  { to: "/radar", label: "Radar" },
  { to: "/board", label: "Board" },
  { to: "/scope", label: "Scope" },
  { to: "/graph", label: "Graf" },
  { to: "/activity", label: "Activity" },
  { to: "/ask", label: "Ask" },
];

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

export default function AppLayout() {
  return (
    <div className="flex h-screen">
      <aside className="flex w-44 flex-col border-r border-border">
        <div className="flex items-center gap-2 px-4 py-4">
          {/* Kesişim logosu placeholder'ı — Pencil'dan gelecek (D-34) */}
          <span className="inline-block size-3 rounded-full bg-primary" aria-hidden />
          <span className="text-sm font-semibold tracking-tight">Ensemble</span>
        </div>
        <nav className="flex-1 space-y-0.5 px-2">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end
              className={({ isActive }) =>
                `block rounded px-2 py-1.5 text-sm ${
                  isActive
                    ? "bg-muted font-medium"
                    : "text-muted-foreground hover:bg-muted/50"
                }`
              }
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
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
            <span className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
              {config.mode}
            </span>
            {/* health noktası — #20 canlandıracak (GET /health) */}
            <span
              className="size-2 rounded-full bg-status-backlog"
              title="Backend bağlantısı bekleniyor (#20)"
            />
            <AuthGostergesi />
          </div>
        </header>
        <main className="min-w-0 flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
