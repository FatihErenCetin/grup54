import { Link } from "react-router-dom";
import { ActorChip, HataDurumu, YuklemeIskeleti } from "../components/ui";
import { config } from "../lib/config";
import { useAuth, useCikisYap } from "../lib/useAuth";

/* Login (#79, S3-stretch — D-23'ün gate'i bu görevle açılıyor) — AppLayout
   DIŞINDA, Landing ile aynı sade çerçeve (bkz. görev brifi §2).

   Giriş hiçbir sayfayı KAPATMAZ (route guard yok, MVP ilkesi): bu sayfa
   yalnız bir kolaylık — GitHub kimliğini bağlamak isteyenler için. Demo
   `/radar`'a girişsiz de açılır, bu yüzden her dalda oraya dürüst bir çıkış
   bırakılır.

   Üç durum + kimlik hâli — RadarPage/AskPage'teki "hook üç durumu döndürür,
   sayfa üçünü de çizer" kalıbının aynısı (ui.tsx yorumu): yükleniyor / gerçek
   hata (401 hariç — o anonim, hata değil) / veri (kullanici|null + enabled). */
export default function LoginPage() {
  const { enabled, kullanici, isLoading, error } = useAuth();

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto max-w-md px-6 py-16">
        <h1 className="text-base font-semibold">Giriş</h1>

        <div className="mt-6">
          {isLoading ? (
            <YuklemeIskeleti label="Giriş durumu yükleniyor" satir={1} />
          ) : error != null ? (
            <HataDurumu baslik="Giriş durumu alınamıyor" hata={error} />
          ) : kullanici ? (
            <GirisliGorunum kullanici={kullanici} />
          ) : enabled ? (
            <GirisYapGorunumu />
          ) : (
            <DevreDisiGorunumu />
          )}
        </div>
      </div>
    </div>
  );
}

function GirisliGorunum({ kullanici }: { kullanici: { handle: string } }) {
  const { cikisYap, yukleniyor, hata } = useCikisYap();
  return (
    <div className="space-y-4 rounded-lg border border-border bg-card p-4">
      <div className="space-y-1">
        <p className="text-xs text-muted-foreground">Giriş yapıldı</p>
        <ActorChip handle={kullanici.handle} type="human" />
      </div>
      <button
        type="button"
        onClick={() => void cikisYap()}
        disabled={yukleniyor}
        className="rounded px-2 py-1 text-xs text-muted-foreground hover:bg-muted/50 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {yukleniyor ? "Çıkış yapılıyor…" : "Çıkış yap"}
      </button>
      {/* Buton kendi başarısızlığını taşır — tüm sayfayı HataDurumu ile kaplamak
          burada aşırı olurdu (AskPage'deki "hata yalnız ilgili alanı kaplar" kalıbı). */}
      {hata != null && (
        <p className="font-mono text-[11px] text-severity-high">
          Çıkış başarısız — tekrar dene.
        </p>
      )}
      <p className="text-xs text-muted-foreground">
        <Link to="/radar" className="underline hover:text-foreground">
          Radar'a dön →
        </Link>
      </p>
    </div>
  );
}

function GirisYapGorunumu() {
  return (
    <div className="space-y-4 rounded-lg border border-border bg-card p-4">
      <p className="text-sm text-muted-foreground">
        GitHub hesabınla giriş yaparsan aktivite/karar geçmişinde kendi adınla
        görünürsün. Bu isteğe bağlıdır.
      </p>
      <a
        href={`${config.apiBaseUrl}/auth/login`}
        className="inline-flex items-center justify-center rounded-lg bg-primary px-4 py-3 text-sm font-medium text-primary-foreground hover:opacity-90"
      >
        GitHub ile devam et
      </a>
      <p className="text-xs text-muted-foreground">
        Giriş şart değil —{" "}
        <Link to="/radar" className="underline hover:text-foreground">
          demoyu girişsiz de açabilirsin
        </Link>
        .
      </p>
    </div>
  );
}

function DevreDisiGorunumu() {
  return (
    <div className="space-y-3 rounded-lg border border-border bg-card p-4">
      <p className="text-sm">GitHub girişi bu kurulumda yapılandırılmamış.</p>
      <p className="text-xs text-muted-foreground">
        Bu bir hata değil — demo, giriş GEREKTİRMEDEN çalışır; aşağıdaki
        sayfaların hepsi açık.
      </p>
      <p className="text-xs">
        <Link to="/radar" className="underline hover:text-foreground">
          Radar'a git →
        </Link>
      </p>
    </div>
  );
}
