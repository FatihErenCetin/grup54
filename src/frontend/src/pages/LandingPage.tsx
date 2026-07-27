import { Link } from "react-router-dom";
import { Card } from "../components/ui";
import { gorunenAd, useAuth } from "../lib/useAuth";

// Repo linki: gerçek origin'den (git remote) — uydurma URL değil.
const REPO_URL = "https://github.com/FatihErenCetin/grup54";

const ADIMLAR = [
  {
    baslik: "Bağla",
    aciklama: "Repo'yu bağla — kurulum tek seferlik.",
  },
  {
    baslik: "Çalışmaya devam et",
    aciklama: "Ekip ve AI ajanları her zamanki gibi çalışır, ekstra adım yok.",
  },
  {
    baslik: "Çakışmadan önce gör",
    aciklama: "İki kişi (ya da ajan) aynı yere dokunmadan önce radarda uyarı çıkar.",
  },
];

/* Landing (#260, T-294 ile Üye ol/Giriş yap eklendi) — AppLayout DIŞINDA,
   kimliksiz + neredeyse STATİK sayfa: demo CTA'sı/video/adımlar hiçbir veri
   çağrısı yapmaz, backend kapalıyken bile açılır (kabul kriteri — DEĞİŞMEDİ).
   Emsal: Evil Martians 100-landing normu — ortalanmış hero + tek başlık +
   ürün görseli + 2 CTA. Kaynak: README.md üst kısmı + internal/urun_aciklamasi.md;
   hiçbir sayı/istatistik uydurulmadı (dogfood metrik bloğu bu yüzden bilinçli
   YOK — gerçek PR/task/uyarı sayısı için canlı veri gerekir, statik sayfa
   yalan söylemesin diye eklenmedi).

   PO şikayeti ("üye ol/giriş yap yok") burada TEK istisnayla kapanıyor:
   sağ üstteki iki link `/auth/config`e göre KOŞULLU (useAuth zaten bunu
   sorguluyor) — `enabled`/`emailEnabled` ikisi de kapalıysa ya da sorgu
   başarısız olursa (backend gerçekten kapalıyken) HİÇBİRİ basılmaz
   ("çalışmayan buton basma", AppLayout kuralı ile aynı ilke); sayfanın geri
   kalanı bundan TAMAMEN bağımsız render olmaya devam eder. */
export default function LandingPage() {
  const { enabled, emailEnabled, kullanici, isLoading, error } = useAuth();
  const authLinkleriGoster = !isLoading && error == null && (enabled || emailEnabled);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto max-w-5xl px-6 py-16">
        {authLinkleriGoster && (
          <div className="mb-8 flex items-center justify-end gap-4 text-xs">
            {kullanici ? (
              <Link to="/login" className="text-muted-foreground hover:text-foreground">
                {gorunenAd(kullanici)} olarak giriş yaptın
              </Link>
            ) : (
              <>
                {emailEnabled && (
                  <Link to="/kayit" className="text-muted-foreground hover:text-foreground">
                    Üye ol
                  </Link>
                )}
                <Link
                  to="/login"
                  className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:opacity-90"
                >
                  Giriş yap
                </Link>
              </>
            )}
          </div>
        )}

        <div className="mx-auto max-w-2xl text-center">
          <p className="text-xs font-medium text-muted-foreground">
            YZTA Bootcamp 2026 · source-available
          </p>

          {/* Tek h1 — konumlandırma cümlesi, tasarım paketi §2 "Landing" */}
          <h1 className="mt-3 text-3xl font-semibold tracking-tight text-balance">
            Ekibin ve AI ajanların çakışmadan önce haber alsın.
          </h1>

          <p className="mt-4 text-sm leading-relaxed text-muted-foreground">
            Ensemble, ekibin GitHub'daki gerçek çalışmasını izler; kim neye
            dokunuyor, kimler çakışmak üzere, nerede plandan sapıldı — hepsini
            tek panoda gösterir.
          </p>

          <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link
              to="/radar"
              className="rounded-md bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground hover:opacity-90"
            >
              Demoyu aç →
            </Link>
            <a
              href={REPO_URL}
              target="_blank"
              rel="noreferrer"
              className="text-sm text-muted-foreground hover:text-foreground"
            >
              GitHub'da incele
            </a>
          </div>
          <p className="mt-2 text-[11px] text-muted-foreground">
            Kayıt yok, kurulum yok — doğrudan çalışan panoya gider.
          </p>
        </div>

        {/* Ürün görseli — ekran görüntüsü YOK (henüz çekilmedi); üç yüzeyi
            (Radar/Scope/Board) CSS ile anlatan soyut önizleme, /radar'a götürür. */}
        <Link
          to="/radar"
          className="group mx-auto mt-12 block max-w-3xl rounded-lg border border-border bg-card p-6 transition-colors hover:border-primary/40"
        >
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
            <div>
              <p className="text-xs font-medium text-muted-foreground">Radar</p>
              <div className="mt-2 space-y-1.5">
                <div className="flex items-center gap-2">
                  <span aria-hidden className="text-severity-high">
                    ▲
                  </span>
                  <span className="h-1.5 flex-1 rounded-full bg-severity-high/25" />
                </div>
                <div className="flex items-center gap-2">
                  <span aria-hidden className="text-severity-med">
                    ◆
                  </span>
                  <span className="h-1.5 w-4/5 rounded-full bg-severity-med/25" />
                </div>
                <div className="flex items-center gap-2">
                  <span aria-hidden className="text-severity-low">
                    ●
                  </span>
                  <span className="h-1.5 w-3/5 rounded-full bg-severity-low/25" />
                </div>
              </div>
            </div>

            <div>
              <p className="text-xs font-medium text-muted-foreground">Scope</p>
              <div className="mt-2 space-y-1.5">
                <div className="flex items-center gap-2">
                  <span aria-hidden className="size-1.5 shrink-0 rounded-full bg-status-done" />
                  <span className="h-1.5 flex-1 rounded-full bg-status-done/25" />
                </div>
                <div className="flex items-center gap-2">
                  <span
                    aria-hidden
                    className="size-1.5 shrink-0 rounded-full bg-status-in-review"
                  />
                  <span className="h-1.5 w-2/3 rounded-full bg-status-in-review/25" />
                </div>
                <div className="flex items-center gap-2">
                  <span aria-hidden className="size-1.5 shrink-0 rounded-full bg-muted-foreground" />
                  <span className="h-1.5 w-1/3 rounded-full bg-muted" />
                </div>
              </div>
            </div>

            <div>
              <p className="text-xs font-medium text-muted-foreground">Board</p>
              <div className="mt-2 grid grid-cols-3 gap-1.5">
                <span className="h-9 rounded bg-status-todo/25" />
                <span className="h-9 rounded bg-status-in-progress/25" />
                <span className="h-9 rounded bg-status-done/25" />
              </div>
            </div>
          </div>

          <p className="mt-5 text-xs text-muted-foreground group-hover:text-foreground">
            Radar · Scope · Board — canlı panoyu görmek için tıkla ↗
          </p>
        </Link>

        {/* Video yeri (#65 ayrı iş) — henüz yok, dürüstçe söylenir; boş <a> YOK */}
        <div className="mx-auto mt-8 max-w-3xl rounded-lg border border-dashed border-border p-6 text-center">
          <p className="text-sm font-medium">3 dakikalık tanıtım</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Video henüz hazır değil — yayınlanınca burada oynatılacak.
          </p>
        </div>

        {/* Nasıl çalışır — 3 kısa adım (tasarım paketi §2 "Landing") */}
        <div className="mx-auto mt-12 grid max-w-3xl grid-cols-1 gap-4 sm:grid-cols-3">
          {ADIMLAR.map((a, i) => (
            <Card key={a.baslik}>
              <p className="font-mono text-xs text-muted-foreground">{i + 1}</p>
              <p className="mt-1 text-sm font-medium">{a.baslik}</p>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                {a.aciklama}
              </p>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
