import { useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { EmptyState, HataDurumu, YuklemeIskeleti } from "../components/ui";
import { useAuth } from "../lib/useAuth";
import {
  kurulumUrlIstegi,
  repolariGuncelle,
  useKurulumlar,
  useRepolar,
  type KurulumOzeti,
  type ReposGuncelleSonucu,
} from "../lib/useRepoSecici";

/* Repo seçici (#79'un kalan dilimi, T-79) — AppLayout İÇİNDE (Login/Register'ın
   aksine): bu, oturum açmış bir kullanıcının uygulama İÇİNDE kullandığı bir
   ayar sayfası, Landing/Login gibi kimliksiz bir giriş noktası DEĞİL.

   Route guard YOK (MVP ilkesi, AGENTS.md) — bu sayfa kendi "giriş gerekli"
   durumunu KENDİSİ çizer (üç-durum kalıbı: yükleniyor / gerçek hata / veri),
   RadarPage/LoginPage'teki gibi. Oturumsuz ziyaretçi buraya gelirse
   `/login`'e yönlendirilir (MUTASYON KİLİDİ — görev brifi: bu dalı kaldır,
   test kırılsın).

   Backend sözleşmesi (auth.py): GET /auth/installations + GET /auth/repos
   ikisi de `_require_session_user_id` arkasında — hem GitHub OAuth hem
   email+parola oturumu (T-79 sonrası ikisi de `sub` taşır) buraya girebilir. */
export default function RepoSeciciPage() {
  const { kullanici, isLoading, error } = useAuth();

  if (isLoading) return <YuklemeIskeleti label="Repo seçici yükleniyor" satir={4} />;
  if (error != null) return <HataDurumu baslik="Giriş durumu alınamıyor" hata={error} />;
  if (!kullanici) return <Navigate to="/login" replace />;

  return <RepoSeciciGovde />;
}

function RepoSeciciGovde() {
  const kurulumlar = useKurulumlar(true);
  const repolar = useRepolar(true);

  if (kurulumlar.isLoading || repolar.isLoading || !kurulumlar.data || !repolar.data) {
    return <YuklemeIskeleti label="Kurulumlar ve repolar yükleniyor" satir={4} />;
  }

  // Oturum ARADA sona ermiş olabilir (çerez süresi, başka sekmede çıkış) —
  // useAuth üstte gördüğü oturumu artık backend GÖRMÜYOR olabilir; aynı
  // "giriş yönlendirmesi" davranışı burada da uygulanır.
  if (kurulumlar.data.tur === "giris_gerekli" || repolar.data.tur === "giris_gerekli") {
    return <Navigate to="/login" replace />;
  }

  if (kurulumlar.data.tur === "kapali") {
    return (
      <div className="space-y-3 rounded-lg border border-border bg-card p-4">
        <h1 className="text-base font-semibold">Repo seçici</h1>
        <p className="text-sm">{kurulumlar.data.mesaj}</p>
        <p className="text-xs text-muted-foreground">
          Bu bir hata değil — bu kurulumda GitHub App entegrasyonu (GITHUB_APP_ID
          ve ilişkili anahtar) henüz eklenmemiş. Demo reposunu görüntülemeye devam
          edebilirsin.
        </p>
        <p className="text-xs">
          <Link to="/radar" className="underline hover:text-foreground">
            Radar'a dön →
          </Link>
        </p>
      </div>
    );
  }

  if (kurulumlar.data.tur === "beklenmeyen") {
    return <HataDurumu baslik="Kurulumlar alınamıyor" hata={kurulumlar.data.mesaj} />;
  }
  if (repolar.data.tur === "beklenmeyen") {
    return <HataDurumu baslik="Repo bilgisi alınamıyor" hata={repolar.data.mesaj} />;
  }

  return (
    <RepoSeciciFormu
      installations={kurulumlar.data.installations}
      selected={repolar.data.selected}
      active={repolar.data.active}
      demo={repolar.data.demo}
    />
  );
}

function GostergeMesaj({ mesaj, ton = "hata" }: { mesaj: string; ton?: "hata" | "basarili" }) {
  const cls =
    ton === "hata"
      ? "border-severity-high/40 bg-severity-high/10 text-severity-high"
      : "border-status-done/40 bg-status-done/10 text-status-done";
  return (
    <p role="alert" className={`rounded-lg border px-3 py-2 text-xs ${cls}`}>
      {mesaj}
    </p>
  );
}

/** GitHub App kurulum sayfasına yönlendiren eylem — hem "hiç kurulum yok"
    boş durumunda hem de var olan listenin altında ("başka bir hesaba/organizasyona
    da kur") kullanılır. Uç bir REDIRECT DEĞİL, `{url}` döner — tarayıcı burada
    manuel yönlendirilir (dosya-başı yorum, useRepoSecici.ts). */
function GitHubKurulumEylemi({ birincil = false }: { birincil?: boolean }) {
  const [yukleniyor, setYukleniyor] = useState(false);
  const [hata, setHata] = useState<string | null>(null);

  async function baslat() {
    setYukleniyor(true);
    setHata(null);
    const s = await kurulumUrlIstegi();
    if (s.tur === "basarili") {
      // Sayfadan ÇIKILIR (GitHub'a gidilir) — state sıfırlamaya gerek yok.
      window.location.href = s.url;
      return;
    }
    setYukleniyor(false);
    if (s.tur === "giris_gerekli") {
      setHata("Oturumun sona ermiş olabilir — tekrar giriş yapman gerekiyor.");
    } else {
      setHata(s.mesaj);
    }
  }

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={() => void baslat()}
        disabled={yukleniyor}
        className={
          birincil
            ? "inline-flex items-center justify-center rounded-lg bg-primary px-4 py-3 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
            : "rounded px-2 py-1 text-xs text-muted-foreground hover:bg-muted/50 disabled:cursor-not-allowed disabled:opacity-60"
        }
      >
        {yukleniyor
          ? "Yönlendiriliyor…"
          : birincil
            ? "GitHub App'i kur"
            : "+ Başka bir hesaba/organizasyona kur"}
      </button>
      {hata != null &&
        (hata.includes("giriş yapman") ? (
          <p className="text-xs text-severity-high">
            {hata}{" "}
            <Link to="/login" className="underline hover:text-foreground">
              Giriş yap →
            </Link>
          </p>
        ) : (
          <GostergeMesaj mesaj={hata} />
        ))}
    </div>
  );
}

/** Kurulumlarda bir tek repo bile YOK — bu bir hata DEĞİL, dürüst boş durum
    (görev brifi §1: "boş liste hata değil"). */
function KurulumYokBosDurum() {
  return (
    <div className="space-y-6">
      <EmptyState
        title="Henüz bir GitHub App kurulumun yok"
        description="Kendi reponu izlemek için önce GitHub App'i kendi hesabına/organizasyonuna kurman gerekiyor — App yalnız senin seçtiğin repolara erişim ister, tüm hesabına değil."
        items={[
          "Kurulum GitHub'ın kendi sayfasında onaylanır, buradan hiçbir şey saklanmaz",
          "Kurulumdan sonra buraya dönüp izlemek istediğin repoları seçeceksin",
        ]}
      />
      <div className="mx-auto max-w-md text-center">
        <GitHubKurulumEylemi birincil />
      </div>
    </div>
  );
}

/** Görev brifi §"DÜRÜSTLÜK" — atlanamaz: kendi reponu aktif yaptığında Scope
    ve Presence'ta ne göreceğini ÖNCEDEN, hata olarak değil bilgi olarak söyler.
    Bu iki sayfaya (ScopePage/PresenceStrip) DOKUNMADIK (görev kapsamı bu ikisi
    değil) — ama onların "yapılandırılmamış"ı "veri yok" ile KARIŞMASIN diye
    burada açıkça yazıyoruz. */
function DurustlukNotu() {
  return (
    <div className="space-y-1.5 rounded-lg border border-status-in-review/40 bg-status-in-review/10 p-3">
      <p className="text-xs font-medium text-status-in-review">
        Kendi reponu seçtiğinde bilmen gerekenler
      </p>
      <ul className="space-y-1 text-xs leading-relaxed text-muted-foreground">
        <li>
          <span className="font-mono">Kapsam</span> sayfası bu repo için{" "}
          <span className="font-mono">.harness/scope/</span> bulamayacak ve "yapılandırılmamış"
          bir hata gösterecek — bu demo reposuna özel bir dosya, senin reponda henüz yok. Bu bir
          arıza değil.
        </li>
        <li>
          "Şu an çalışanlar" şeridi (Presence) boş görünecek — ama bu "kimse çalışmıyor" demek
          DEĞİL; verinin kaynağı olan <span className="font-mono">.harness/active/</span> senin
          reponda yok, bu yüzden uç her zaman boş liste döner.
        </li>
        <li>
          Commit/PR/issue akışı (Radar/Board/Activity) GitHub webhook'u geldikçe dolar — kurulum
          anında değil, ilk olay geldiğinde.
        </li>
      </ul>
    </div>
  );
}

function RepoSatiri({
  repo,
  seciliMi,
  aktifMi,
  onSeciliDegisti,
  onAktifSecildi,
}: {
  repo: { full_name: string; private: boolean };
  seciliMi: boolean;
  aktifMi: boolean;
  onSeciliDegisti: (secili: boolean) => void;
  onAktifSecildi: () => void;
}) {
  const inputId = `repo-${repo.full_name}`;
  return (
    <div className="flex items-center justify-between gap-3 border-b border-border px-3 py-2 last:border-0">
      <label htmlFor={inputId} className="flex min-w-0 items-center gap-2 text-sm">
        <input
          id={inputId}
          type="checkbox"
          checked={seciliMi}
          onChange={(e) => onSeciliDegisti(e.target.checked)}
        />
        <span className="truncate font-mono text-xs">{repo.full_name}</span>
        {repo.private && (
          <span className="rounded bg-muted px-1 py-0.5 text-[10px] text-muted-foreground">
            özel
          </span>
        )}
      </label>
      <label
        className={`flex shrink-0 items-center gap-1.5 text-xs ${
          seciliMi ? "text-muted-foreground" : "cursor-not-allowed text-muted-foreground/40"
        }`}
      >
        <input
          type="radio"
          name="aktif-repo"
          disabled={!seciliMi}
          checked={aktifMi}
          onChange={onAktifSecildi}
        />
        aktif
      </label>
    </div>
  );
}

function RepoSeciciFormu({
  installations,
  selected,
  active,
  demo,
}: {
  installations: KurulumOzeti[];
  selected: string[];
  active: string | null;
  demo: string | null;
}) {
  // Yalnız İLK başarılı yükte hidrate edilir (lazy initializer) — arka plan
  // yeniden-çekimi (odağa dönüş) kullanıcının İŞLEMEKTE olduğu seçimi EZMEZ.
  const [seciliRepolar, setSeciliRepolar] = useState<Set<string>>(() => new Set(selected));
  const [aktifRepo, setAktifRepo] = useState<string | null>(active);
  const [kaydediliyor, setKaydediliyor] = useState(false);
  const [sonuc, setSonuc] = useState<ReposGuncelleSonucu | null>(null);

  const tumRepolar = installations.flatMap((k) =>
    k.repos.map((r) => ({ ...r, installation: k.account_login })),
  );

  function repoDegisti(fullName: string, secili: boolean) {
    setSonuc(null);
    setSeciliRepolar((onceki) => {
      const yeni = new Set(onceki);
      if (secili) yeni.add(fullName);
      else yeni.delete(fullName);
      return yeni;
    });
    // Seçimden çıkarılan repo aktifse aktiflik de düşer — "seçili olmayan bir
    // repo aktif" durumu istemci tarafında hiç OLUŞTURULMAZ.
    if (!secili && aktifRepo === fullName) setAktifRepo(null);
  }

  async function kaydet() {
    setKaydediliyor(true);
    setSonuc(null);
    const s = await repolariGuncelle([...seciliRepolar], aktifRepo);
    setKaydediliyor(false);
    setSonuc(s);
    if (s.tur === "basarili") {
      setSeciliRepolar(new Set(s.selected));
      setAktifRepo(s.active);
    }
  }

  return (
    <div className="max-w-2xl space-y-5">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-base font-semibold">Repo seçici</h1>
      </div>

      <DurustlukNotu />

      {demo && (
        <p className="text-xs text-muted-foreground">
          Demo repo: <span className="font-mono">{demo}</span> — hiç repo seçmesen/aktif
          yapmasan da bu her zaman görülebilir kalır.
        </p>
      )}

      {tumRepolar.length === 0 ? (
        <KurulumYokBosDurum />
      ) : (
        <div className="space-y-4">
          <div className="overflow-hidden rounded-lg border border-border bg-card">
            <label className="flex items-center justify-between gap-3 border-b border-border bg-muted/30 px-3 py-2 text-xs">
              <span className="flex items-center gap-2">
                <input
                  type="radio"
                  name="aktif-repo"
                  checked={aktifRepo === null}
                  onChange={() => setAktifRepo(null)}
                />
                Demo reposunu görüntüle
              </span>
              {demo && <span className="font-mono text-muted-foreground">{demo}</span>}
            </label>
            {tumRepolar.map((r) => (
              <RepoSatiri
                key={r.full_name}
                repo={r}
                seciliMi={seciliRepolar.has(r.full_name)}
                aktifMi={aktifRepo === r.full_name}
                onSeciliDegisti={(secili) => repoDegisti(r.full_name, secili)}
                onAktifSecildi={() => setAktifRepo(r.full_name)}
              />
            ))}
          </div>

          {sonuc && sonuc.tur === "basarili" && (
            <GostergeMesaj
              ton="basarili"
              mesaj={
                aktifRepo
                  ? `Kaydedildi — artık ${aktifRepo} reposuna bakıyorsun.`
                  : "Kaydedildi — demo reposuna bakıyorsun."
              }
            />
          )}
          {sonuc && sonuc.tur === "izinsiz" && <GostergeMesaj mesaj={sonuc.mesaj} />}
          {sonuc && sonuc.tur === "beklenmeyen" && <GostergeMesaj mesaj={sonuc.mesaj} />}
          {sonuc && sonuc.tur === "giris_gerekli" && (
            <GostergeMesaj mesaj="Oturumun sona ermiş olabilir — tekrar giriş yapman gerekiyor." />
          )}

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => void kaydet()}
              disabled={kaydediliyor}
              className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:cursor-not-allowed disabled:bg-muted disabled:text-muted-foreground"
            >
              {kaydediliyor ? "Kaydediliyor…" : "Kaydet"}
            </button>
            {sonuc?.tur === "basarili" && (
              <Link to="/radar" className="text-xs underline hover:text-foreground">
                Radar'a git →
              </Link>
            )}
          </div>

          <GitHubKurulumEylemi />
        </div>
      )}
    </div>
  );
}
