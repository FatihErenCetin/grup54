import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ActorChip, AuthSonucMesaji, HataDurumu, YuklemeIskeleti } from "../components/ui";
import {
  kayitOlIstegi,
  gorunenAd,
  useAuth,
  type AuthEylemSonucu,
  type AuthKullanici,
} from "../lib/useAuth";

const PAROLA_MIN = 8;
const PAROLA_MAX = 128;

/* Kayıt (/kayit, T-294/D-57) — AppLayout DIŞINDA, Landing/Login ile aynı sade
   çerçeve. PO şikayeti: "landing'de üye ol ve giriş yap yok" — bu sayfa email
   + parola üyeliğinin GERÇEK giriş noktası.

   DÜRÜSTLÜK (D-57 "bilerek yapılmayan", görev brifi madde 5) — atlanamaz:
   email doğrulaması ve parola sıfırlama YOK (SMTP yapılandırılmamış). Bu
   sayfa formu her zaman bu uyarıyla birlikte gösterir — hata olduğunda değil,
   HER ZAMAN (kullanıcı "doğrulama e-postası" bekleyip beklememesi gerektiğini
   göndermeden ÖNCE bilsin). "Şifremi unuttum" bağlantısı bilinçli YOK
   (çalışmıyor — AppLayout'taki "çalışmayan buton basma" kuralı).

   Parola politikası (8–128) ÖNCEDEN yazılır — backend'in 422'sini beklemeden;
   backend zaten aynı sınırı uyguluyor (credentials.py MIN/MAX_PASSWORD_LENGTH,
   tek kaynak), burada aynı sayılar TEKRARLANIR (kopya değil, kullanıcıya
   erken-uyarı). Parola tekrarı istemci tarafında kontrol edilir — uyuşmazsa
   istek hiç ATILMAZ (gereksiz 422 turu + backend'e boşuna yük). */
export default function RegisterPage() {
  const { enabled, emailEnabled, kullanici, isLoading, error } = useAuth();

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto max-w-md px-6 py-16">
        <h1 className="text-base font-semibold">Kayıt ol</h1>

        <div className="mt-6">
          {isLoading ? (
            <YuklemeIskeleti label="Kayıt durumu yükleniyor" satir={1} />
          ) : error != null ? (
            <HataDurumu baslik="Kayıt durumu alınamıyor" hata={error} />
          ) : kullanici ? (
            <ZatenGirisliGorunum kullanici={kullanici} />
          ) : emailEnabled ? (
            <KayitFormu />
          ) : (
            <DevreDisiGorunumu githubAcik={enabled} />
          )}
        </div>
      </div>
    </div>
  );
}

function ZatenGirisliGorunum({ kullanici }: { kullanici: AuthKullanici }) {
  return (
    <div className="space-y-3 rounded-lg border border-border bg-card p-4">
      <div className="space-y-1">
        <p className="text-xs text-muted-foreground">Zaten giriş yapılmış</p>
        <ActorChip handle={gorunenAd(kullanici)} type="human" />
      </div>
      <p className="text-xs text-muted-foreground">
        Yeni bir hesap açmak için önce{" "}
        <Link to="/login" className="underline hover:text-foreground">
          çıkış yap
        </Link>
        , ya da doğrudan{" "}
        <Link to="/radar" className="underline hover:text-foreground">
          Radar'a dön
        </Link>
        .
      </p>
    </div>
  );
}

function KayitFormu() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [parola, setParola] = useState("");
  const [parolaTekrar, setParolaTekrar] = useState("");
  const [eslesmeHatasi, setEslesmeHatasi] = useState(false);
  const [gonderiliyor, setGonderiliyor] = useState(false);
  const [sonuc, setSonuc] = useState<AuthEylemSonucu | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    // Parola tekrarı BURADA, isteği ATMADAN ÖNCE kontrol edilir (görev brifi
    // mutasyon kilidi) — uyuşmazsa `kayitOlIstegi` hiç ÇAĞRILMAZ.
    if (parola !== parolaTekrar) {
      setEslesmeHatasi(true);
      setSonuc(null);
      return;
    }
    setEslesmeHatasi(false);
    setGonderiliyor(true);
    setSonuc(null);
    const s = await kayitOlIstegi(email, parola);
    if (s.tur === "basarili") {
      // Sahte-canlılık yasak (D-34): /radar'a geçilir, AppLayout kendi
      // useAuth'unu YENİDEN çalıştırıp GERÇEK oturumu sunucudan tazeler.
      navigate("/radar");
      return;
    }
    setGonderiliyor(false);
    setSonuc(s);
  }

  return (
    <div className="space-y-4 rounded-lg border border-border bg-card p-4">
      {/* Dürüstlük uyarısı — HER ZAMAN görünür (hata değil, önceden bilgi;
          bkz. dosya-başı yorum). "Doğrulama e-postası gönderildi" gibi bir
          cümle bu uygulamada HİÇBİR YERDE kurulmaz. */}
      <div className="rounded-lg border border-status-in-review/40 bg-status-in-review/10 p-3">
        <p className="text-xs font-medium text-status-in-review">
          E-posta doğrulaması ve parola sıfırlama bu sürümde yok
        </p>
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
          Hesabın oluşturur oluşturmaz aktif olur, e-posta adresine hiçbir şey
          gönderilmez. Parolanı unutursan bu sürümde sıfırlama yolu yok —
          güvenip hatırlayabileceğin bir parola seç.
        </p>
      </div>

      <form onSubmit={(e) => void submit(e)} className="space-y-3">
        <div className="space-y-1">
          <label htmlFor="kayit-email" className="text-xs text-muted-foreground">
            E-posta
          </label>
          <input
            id="kayit-email"
            type="email"
            required
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:border-foreground/25"
          />
        </div>

        <div className="space-y-1">
          <label htmlFor="kayit-parola" className="text-xs text-muted-foreground">
            Parola
          </label>
          <input
            id="kayit-parola"
            type="password"
            required
            minLength={PAROLA_MIN}
            maxLength={PAROLA_MAX}
            autoComplete="new-password"
            value={parola}
            onChange={(e) => setParola(e.target.value)}
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:border-foreground/25"
          />
          {/* Politika ÖNCEDEN söylenir — backend'in 422'sini beklemeden (görev
              brifi: "hatayı sonradan patlatma"). */}
          <p className="text-[11px] text-muted-foreground">
            {PAROLA_MIN}–{PAROLA_MAX} karakter arası olmalı.
          </p>
        </div>

        <div className="space-y-1">
          <label htmlFor="kayit-parola-tekrar" className="text-xs text-muted-foreground">
            Parola (tekrar)
          </label>
          <input
            id="kayit-parola-tekrar"
            type="password"
            required
            autoComplete="new-password"
            value={parolaTekrar}
            onChange={(e) => {
              setParolaTekrar(e.target.value);
              if (eslesmeHatasi) setEslesmeHatasi(false);
            }}
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:border-foreground/25"
          />
        </div>

        {eslesmeHatasi && (
          <p role="alert" className="rounded-lg border border-severity-high/40 bg-severity-high/10 px-3 py-2 text-xs text-severity-high">
            Parolalar eşleşmiyor.
          </p>
        )}
        {!eslesmeHatasi && sonuc && sonuc.tur !== "basarili" && <AuthSonucMesaji sonuc={sonuc} />}

        <button
          type="submit"
          disabled={gonderiliyor || email === "" || parola === "" || parolaTekrar === ""}
          className="w-full rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:cursor-not-allowed disabled:bg-muted disabled:text-muted-foreground"
        >
          {gonderiliyor ? "Kayıt oluşturuluyor…" : "Kayıt ol"}
        </button>
      </form>

      <p className="text-xs text-muted-foreground">
        Zaten hesabın var mı?{" "}
        <Link to="/login" className="underline hover:text-foreground">
          Giriş yap
        </Link>
      </p>
    </div>
  );
}

function DevreDisiGorunumu({ githubAcik }: { githubAcik: boolean }) {
  return (
    <div className="space-y-3 rounded-lg border border-border bg-card p-4">
      <p className="text-sm">E-posta ile üyelik bu kurulumda yapılandırılmamış.</p>
      <p className="text-xs text-muted-foreground">
        Bu bir hata değil — demo, giriş GEREKTİRMEDEN çalışır; aşağıdaki
        sayfaların hepsi açık.
      </p>
      <p className="text-xs">
        <Link to="/radar" className="underline hover:text-foreground">
          Radar'a git →
        </Link>
        {githubAcik && (
          <>
            {" · "}
            <Link to="/login" className="underline hover:text-foreground">
              GitHub ile giriş dene →
            </Link>
          </>
        )}
      </p>
    </div>
  );
}
