import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ActorChip, AuthSonucMesaji, HataDurumu, YuklemeIskeleti } from "../components/ui";
import { config } from "../lib/config";
import {
  girisYapIstegi,
  gorunenAd,
  useAuth,
  useCikisYap,
  type AuthEylemSonucu,
  type AuthKullanici,
} from "../lib/useAuth";

/* Login (#79, S3-stretch — D-23'ün gate'i bu görevle açılıyor; T-294/D-57 ile
   GitHub OAuth'un YANINA email+parola formu eklendi) — AppLayout DIŞINDA,
   Landing ile aynı sade çerçeve (bkz. görev brifi §2).

   Giriş hiçbir sayfayı KAPATMAZ (route guard yok, MVP ilkesi): bu sayfa
   yalnız bir kolaylık — kimlik bağlamak isteyenler için. Demo `/radar`'a
   girişsiz de açılır, bu yüzden her dalda oraya dürüst bir çıkış bırakılır.

   İKİ AYRI KAPI (D-57): `enabled` = GitHub OAuth, `emailEnabled` = email
   üyeliği — birbirinden BAĞIMSIZ, sayfa her ikisini de ayrı ayrı sorar ve
   yalnız açık olanı çizer ("çalışmayan buton basma" — AppLayout kuralı).

   Üç durum + kimlik hâli — RadarPage/AskPage'teki "hook üç durumu döndürür,
   sayfa üçünü de çizer" kalıbının aynısı (ui.tsx yorumu): yükleniyor / gerçek
   hata (401 hariç — o anonim, hata değil) / veri (kullanici|null + iki kapı). */
export default function LoginPage() {
  const { enabled, emailEnabled, kullanici, isLoading, error } = useAuth();

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
          ) : enabled || emailEnabled ? (
            <GirisSecenekleri githubAcik={enabled} emailAcik={emailEnabled} />
          ) : (
            <DevreDisiGorunumu />
          )}
        </div>
      </div>
    </div>
  );
}

function GirisliGorunum({ kullanici }: { kullanici: AuthKullanici }) {
  const { cikisYap, yukleniyor, hata } = useCikisYap();
  return (
    <div className="space-y-4 rounded-lg border border-border bg-card p-4">
      <div className="space-y-1">
        <p className="text-xs text-muted-foreground">Giriş yapıldı</p>
        <ActorChip handle={gorunenAd(kullanici)} type="human" />
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

/** GitHub butonu + email formu — ikisi de KOŞULLU, en az biri açık olduğu
    için buraya girildi (kapsayıcı `enabled || emailEnabled` kontrolü zaten
    LoginPage'te). İkisi birden açıksa aralarına ince bir ayraç konur. */
function GirisSecenekleri({
  githubAcik,
  emailAcik,
}: {
  githubAcik: boolean;
  emailAcik: boolean;
}) {
  return (
    <div className="space-y-4 rounded-lg border border-border bg-card p-4">
      {githubAcik && (
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">
            GitHub hesabınla giriş yaparsan aktivite/karar geçmişinde kendi adınla
            görünürsün. Bu isteğe bağlıdır.
          </p>
          <a
            href={`${config.apiBaseUrl}/auth/login`}
            className="inline-flex w-full items-center justify-center rounded-lg bg-primary px-4 py-3 text-sm font-medium text-primary-foreground hover:opacity-90"
          >
            GitHub ile devam et
          </a>
        </div>
      )}

      {githubAcik && emailAcik && (
        <div className="flex items-center gap-2" aria-hidden>
          <span className="h-px flex-1 bg-border" />
          <span className="text-[11px] text-muted-foreground">veya</span>
          <span className="h-px flex-1 bg-border" />
        </div>
      )}

      {emailAcik && <EmailGirisFormu />}

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

function EmailGirisFormu() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [parola, setParola] = useState("");
  const [gonderiliyor, setGonderiliyor] = useState(false);
  const [sonuc, setSonuc] = useState<AuthEylemSonucu | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setGonderiliyor(true);
    setSonuc(null);
    const s = await girisYapIstegi(email, parola);
    if (s.tur === "basarili") {
      // Sahte-canlılık yasak (D-34): state iyimser doldurulmaz — /radar'a
      // geçilir, oradaki AppLayout kendi useAuth'unu YENİDEN çalıştırıp
      // GERÇEK oturumu sunucudan tazeler.
      navigate("/radar");
      return;
    }
    setGonderiliyor(false);
    setSonuc(s);
  }

  return (
    <form onSubmit={(e) => void submit(e)} className="space-y-3">
      <div className="space-y-1">
        <label htmlFor="giris-email" className="text-xs text-muted-foreground">
          E-posta
        </label>
        <input
          id="giris-email"
          type="email"
          required
          autoComplete="username"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:border-foreground/25"
        />
      </div>
      <div className="space-y-1">
        <label htmlFor="giris-parola" className="text-xs text-muted-foreground">
          Parola
        </label>
        <input
          id="giris-parola"
          type="password"
          required
          autoComplete="current-password"
          value={parola}
          onChange={(e) => setParola(e.target.value)}
          className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:border-foreground/25"
        />
      </div>

      {/* != null: openapi-fetch boş gövdeli non-ok cevapta error="" (falsy!)
          verebilir — ama burada zaten `AuthEylemSonucu.tur`a göre dallandık,
          bu satır yalnız "henüz sonuç yok" (null) hâlini eler. */}
      {sonuc && sonuc.tur !== "basarili" && <AuthSonucMesaji sonuc={sonuc} />}

      <button
        type="submit"
        disabled={gonderiliyor || email === "" || parola === ""}
        className="w-full rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:cursor-not-allowed disabled:bg-muted disabled:text-muted-foreground"
      >
        {gonderiliyor ? "Giriş yapılıyor…" : "E-posta ile giriş yap"}
      </button>
    </form>
  );
}

function DevreDisiGorunumu() {
  return (
    <div className="space-y-3 rounded-lg border border-border bg-card p-4">
      <p className="text-sm">Giriş bu kurulumda yapılandırılmamış.</p>
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
