import { useState } from "react";
import { Navigate } from "react-router-dom";
import { HataDurumu, YuklemeIskeleti } from "../components/ui";
import {
  saglayiciGuncelle,
  saglayiciTestEt,
  useMcpConfig,
  useSaglayiciAyarlari,
  type McpAracConfig,
  type McpConfigSonucu,
  type SaglayiciAyarlari,
  type SaglayiciGuncelleSonucu,
  type SaglayiciTestSonucu,
  type SaglayiciTuru,
} from "../lib/useSettings";

/* Ayarlar (/ayarlar, T-309) — PO isteği: "lokaldeki veya kullanıcıların sahip
   olduğu API'lerle çalışabilme" + "Claude Code'a bağlama kısmı". Backend
   T-307'de bitti (#307/#308, merge edildi) — bu sayfa YALNIZ tüketim.

   Route guard YOK ama BAŞKA bir kapı var (RepoSeciciPage'in "giriş gerekli"
   kapısının SİMETRİĞİ, oturum yerine MOD): `GET /settings/saglayici` yalnız
   local modda 200 döner, hosted'da 404 — bu sayfa doğrudan `/ayarlar`'a
   giden biri için 404'ü Radar'a yumuşak bir Navigate'e çevirir; "ölü sayfa"
   göstermez ("çalışmayan sekme basmıyoruz" ilkesi, AppLayout dosya-başı
   yorumu).

   #332 — O KAPI DARALDI: sayfada artık moddan BAĞIMSIZ çalışan bir bölüm var
   (MCP bağlanma reçetesi; `GET /settings/mcp` hosted'da da 200 döner, çünkü
   MCP her hâlükârda kullanıcının KENDİ makinesinde bir stdio süreci olarak
   koşar). Bu yüzden Radar'a yönlendirme artık "sağlayıcı ucu 404" ile değil,
   "gösterilecek HİÇBİR şey yok" (sağlayıcı YOK **ve** MCP YOK) ile tetiklenir
   — aksi hâlde hosted kullanıcı bağlanma yolunu hiç göremezdi (kabul kriteri:
   "sessiz 404 kalmaz").

   Sahte-canlılık yasak (D-34): kaydetme SONRASI yerel durum backend'in
   DÖNDÜĞÜ tam zarfla değiştirilir (RepoSeciciFormu'nun aynı kalıbı) —
   iyimser güncelleme YOK. */
export default function AyarlarPage() {
  const ayarlar = useSaglayiciAyarlari();
  const mcpSorgu = useMcpConfig(true);

  if (ayarlar.isLoading || !ayarlar.data || mcpSorgu.isLoading) {
    return <YuklemeIskeleti label="Ayarlar yükleniyor" satir={4} />;
  }
  const mcp = mcpSorgu.data;
  if (ayarlar.data.tur === "yok" && mcp?.tur !== "basarili") {
    return <Navigate to="/radar" replace />;
  }
  if (ayarlar.data.tur === "beklenmeyen") {
    return <HataDurumu baslik="Ayarlar alınamıyor" hata={ayarlar.data.mesaj} />;
  }

  return (
    <AyarlarGovde ayar={ayarlar.data.tur === "basarili" ? ayarlar.data : null} mcp={mcp} />
  );
}

function AyarlarGovde({
  ayar,
  mcp,
}: {
  ayar: ({ tur: "basarili" } & SaglayiciAyarlari) | null;
  mcp: McpConfigSonucu | undefined;
}) {
  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-base font-semibold">Ayarlar</h1>
        <p className="mt-1 text-xs text-muted-foreground">
          {ayar ? (
            <>
              Kendi API anahtarını gir ya da AI aracını bu projeye bağla.
              Anahtarlar bu makinede kalır (
              <span className="font-mono">~/.ensemble/ayarlar.json</span>),
              repoya/sunucuya asla gönderilmez.
            </>
          ) : (
            // Hosted: sağlayıcı ayarları YOK (anahtarlar sunucunun, kimseye
            // açılmaz) — ama MCP bağlanma reçetesi var. Bunu söylemeden
            // yalnız yarım sayfa göstermek sessiz düşüş olurdu.
            <>
              Bu kurulumda API anahtarı ayarları yok (anahtarlar sunucuya ait,
              tarayıcıdan değiştirilemez). Aşağıda AI aracını kendi makinende
              bu projeye nasıl bağlayacağın yazıyor.
            </>
          )}
        </p>
      </div>

      {ayar && <SaglayiciBolumuKapsayici ayar={ayar} />}
      <McpBolumu mcp={mcp} />
    </div>
  );
}

function SaglayiciBolumuKapsayici({ ayar }: { ayar: { tur: "basarili" } & SaglayiciAyarlari }) {
  const [durum, setDurum] = useState<SaglayiciAyarlari>(ayar);
  return <SaglayiciBolumu durum={durum} onGuncelle={setDurum} />;
}

function SonucMesaji({ mesaj, ton }: { mesaj: string; ton: "hata" | "basarili" }) {
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

function AktifRozeti() {
  return (
    <span className="rounded bg-status-done/15 px-1.5 py-0.5 text-[10px] font-medium text-status-done">
      aktif
    </span>
  );
}

/** `basarili` dışındaki her `tur` için gösterilecek TEK metin — üç kartın
    (Gemini/Ollama/Groq) hepsi bunu paylaşır, ayrı ayrı yazılsaydı biri
    güncellenip diğeri unutulabilirdi (drift). */
function guncelleHataMesaji(s: SaglayiciGuncelleSonucu): string | null {
  switch (s.tur) {
    case "basarili":
      return null;
    case "yok":
      return "Bu uç bu kurulumda yok (hosted).";
    case "gecersiz":
    case "beklenmeyen":
      return s.mesaj;
  }
}

function testSonucGorunumu(s: SaglayiciTestSonucu): { ton: "hata" | "basarili"; mesaj: string } {
  switch (s.tur) {
    case "sonuc":
      // calisiyor:false BİR HATA DEĞİL — dürüst bir bulgu; yine de görsel
      // olarak "hata" tonunda gösterilir (kullanıcı ayırt edebilsin), ama
      // backend'in KENDİ mesajı AYNEN basılır, kendi yorumumuz İCAT EDİLMEZ.
      return { ton: s.calisiyor ? "basarili" : "hata", mesaj: s.mesaj };
    case "yok":
      return { ton: "hata", mesaj: "Bu uç bu kurulumda yok (hosted)." };
    case "gecersiz":
    case "beklenmeyen":
      return { ton: "hata", mesaj: s.mesaj };
  }
}

function TestButonu({ saglayici }: { saglayici: SaglayiciTuru }) {
  const [testEdiliyor, setTestEdiliyor] = useState(false);
  const [sonuc, setSonuc] = useState<SaglayiciTestSonucu | null>(null);

  async function calistir() {
    setTestEdiliyor(true);
    setSonuc(null);
    // Backend'in KENDİ ağ çağrısına dayanır — burada uydurma bir "başarılı"
    // ÜRETİLMEZ (görev brifi: "backend ne diyorsa onu göster").
    const s = await saglayiciTestEt(saglayici);
    setTestEdiliyor(false);
    setSonuc(s);
  }

  return (
    <div className="space-y-1.5">
      <button
        type="button"
        onClick={() => void calistir()}
        disabled={testEdiliyor}
        className="rounded px-2 py-1 text-xs text-muted-foreground hover:bg-muted/50 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {testEdiliyor ? "Test ediliyor…" : "Bağlantıyı test et"}
      </button>
      {sonuc && <SonucMesaji {...testSonucGorunumu(sonuc)} />}
    </div>
  );
}

function SaglayiciBolumu({
  durum,
  onGuncelle,
}: {
  durum: SaglayiciAyarlari;
  onGuncelle: (yeni: SaglayiciAyarlari) => void;
}) {
  return (
    <div className="space-y-3">
      <h2 className="text-sm font-semibold">Sağlayıcı seçimi</h2>
      <p className="text-xs text-muted-foreground">
        Şu an aktif:{" "}
        <span className="font-medium text-foreground">
          {durum.saglayici === "gemini" ? "Gemini" : "Ollama"}
        </span>
      </p>
      <GeminiKarti
        aktifMi={durum.saglayici === "gemini"}
        mevcutMaskeli={durum.anahtarlar.gemini ?? null}
        onKaydedildi={onGuncelle}
      />
      <OllamaKarti
        aktifMi={durum.saglayici === "ollama"}
        mevcutUrl={durum.ollama_url}
        onKaydedildi={onGuncelle}
      />
      <GroqKarti mevcutMaskeli={durum.anahtarlar.groq ?? null} onKaydedildi={onGuncelle} />
    </div>
  );
}

function GeminiKarti({
  aktifMi,
  mevcutMaskeli,
  onKaydedildi,
}: {
  aktifMi: boolean;
  mevcutMaskeli: string | null;
  onKaydedildi: (yeni: SaglayiciAyarlari) => void;
}) {
  const [anahtar, setAnahtar] = useState("");
  const [kaydediliyor, setKaydediliyor] = useState(false);
  const [sonuc, setSonuc] = useState<SaglayiciGuncelleSonucu | null>(null);

  async function kaydet() {
    setKaydediliyor(true);
    setSonuc(null);
    // Input boşsa `anahtar` HİÇ gönderilmez (undefined, boş string DEĞİL) —
    // backend bunu "değiştirme" olarak okur, mevcut anahtar KORUNUR.
    // Maskelenmiş değeri (`ANAH…4f2c`) geri göndermek gerçek anahtarı BOZARDI.
    const s = await saglayiciGuncelle({ saglayici: "gemini", anahtar: anahtar || undefined });
    setKaydediliyor(false);
    setSonuc(s);
    if (s.tur === "basarili") {
      onKaydedildi(s);
      setAnahtar("");
    }
  }

  const hata = sonuc ? guncelleHataMesaji(sonuc) : null;

  return (
    <div className="space-y-2 rounded-lg border border-border bg-card p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium">Gemini</h3>
        {aktifMi && <AktifRozeti />}
      </div>
      <div className="space-y-1">
        <label htmlFor="gemini-anahtar" className="text-xs text-muted-foreground">
          API anahtarı
          {mevcutMaskeli && <span className="ml-1 font-mono">— kayıtlı: {mevcutMaskeli}</span>}
        </label>
        <input
          id="gemini-anahtar"
          type="password"
          autoComplete="off"
          placeholder={mevcutMaskeli ? "Değiştirmek için yeni anahtar gir" : "Anahtarını yapıştır"}
          value={anahtar}
          onChange={(e) => setAnahtar(e.target.value)}
          className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm font-mono focus:border-foreground/25"
        />
      </div>
      {hata && <SonucMesaji ton="hata" mesaj={hata} />}
      {sonuc?.tur === "basarili" && (
        <SonucMesaji ton="basarili" mesaj="Kaydedildi — Gemini şimdi aktif sağlayıcı." />
      )}
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => void kaydet()}
          disabled={kaydediliyor}
          className="rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:opacity-90 disabled:cursor-not-allowed disabled:bg-muted disabled:text-muted-foreground"
        >
          {kaydediliyor ? "Kaydediliyor…" : "Aktif yap ve kaydet"}
        </button>
        <TestButonu saglayici="gemini" />
      </div>
      <p className="text-[11px] text-muted-foreground">
        "Bağlantıyı test et" sunucudaki EN SON KAYDEDİLMİŞ anahtarı kullanır —
        yeni anahtarı test etmeden önce kaydet.
      </p>
    </div>
  );
}

function OllamaKarti({
  aktifMi,
  mevcutUrl,
  onKaydedildi,
}: {
  aktifMi: boolean;
  mevcutUrl: string;
  onKaydedildi: (yeni: SaglayiciAyarlari) => void;
}) {
  const [url, setUrl] = useState(mevcutUrl);
  const [kaydediliyor, setKaydediliyor] = useState(false);
  const [sonuc, setSonuc] = useState<SaglayiciGuncelleSonucu | null>(null);

  async function kaydet() {
    setKaydediliyor(true);
    setSonuc(null);
    const s = await saglayiciGuncelle({ saglayici: "ollama", ollama_url: url || undefined });
    setKaydediliyor(false);
    setSonuc(s);
    if (s.tur === "basarili") {
      onKaydedildi(s);
      setUrl(s.ollama_url);
    }
  }

  const hata = sonuc ? guncelleHataMesaji(sonuc) : null;

  return (
    <div className="space-y-2 rounded-lg border border-border bg-card p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium">Ollama (yerel)</h3>
        {aktifMi && <AktifRozeti />}
      </div>
      <div className="space-y-1">
        <label htmlFor="ollama-url" className="text-xs text-muted-foreground">
          Sunucu adresi (bu bir anahtar DEĞİL — yerelde çalışan Ollama'nın adresi)
        </label>
        <input
          id="ollama-url"
          type="text"
          autoComplete="off"
          placeholder="http://localhost:11434"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm font-mono focus:border-foreground/25"
        />
      </div>
      {hata && <SonucMesaji ton="hata" mesaj={hata} />}
      {sonuc?.tur === "basarili" && (
        <SonucMesaji ton="basarili" mesaj="Kaydedildi — Ollama şimdi aktif sağlayıcı." />
      )}
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => void kaydet()}
          disabled={kaydediliyor}
          className="rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:opacity-90 disabled:cursor-not-allowed disabled:bg-muted disabled:text-muted-foreground"
        >
          {kaydediliyor ? "Kaydediliyor…" : "Aktif yap ve kaydet"}
        </button>
        <TestButonu saglayici="ollama" />
      </div>
    </div>
  );
}

/** Groq — backend'de HİÇBİR ZAMAN "aktif sağlayıcı" (`ProviderSettingsResponse.
    saglayici`) olamaz, yalnız Gemini birincilken devreye giren bir yedek
    anahtar slotu (settings.py: `saglayici in ("gemini","ollama")` koşulu
    Groq'u KAPSAMAZ). Bu yüzden GeminiKarti/OllamaKarti'nin AKSİNE "aktif yap"
    butonu ve rozeti YOK — icat edilmiş bir yetenek göstermemek için bilinçli
    fark (backend'in gerçekten yapamadığı bir şeyi arayüzde "yapılabilir" gibi
    göstermek dürüstlük ilkesine aykırı olurdu). */
function GroqKarti({
  mevcutMaskeli,
  onKaydedildi,
}: {
  mevcutMaskeli: string | null;
  onKaydedildi: (yeni: SaglayiciAyarlari) => void;
}) {
  const [anahtar, setAnahtar] = useState("");
  const [kaydediliyor, setKaydediliyor] = useState(false);
  const [sonuc, setSonuc] = useState<SaglayiciGuncelleSonucu | null>(null);

  async function kaydet() {
    setKaydediliyor(true);
    setSonuc(null);
    const s = await saglayiciGuncelle({ saglayici: "groq", anahtar: anahtar || undefined });
    setKaydediliyor(false);
    setSonuc(s);
    if (s.tur === "basarili") {
      onKaydedildi(s);
      setAnahtar("");
    }
  }

  const hata = sonuc ? guncelleHataMesaji(sonuc) : null;

  return (
    <div className="space-y-2 rounded-lg border border-border bg-card p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium">Groq (yedek)</h3>
        <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
          yedek anahtar
        </span>
      </div>
      <p className="text-[11px] text-muted-foreground">
        Groq tek başına "aktif sağlayıcı" yapılamaz — yalnız Gemini
        birincilken otomatik devreye giren bir yedek anahtar slotu.
      </p>
      <div className="space-y-1">
        <label htmlFor="groq-anahtar" className="text-xs text-muted-foreground">
          API anahtarı
          {mevcutMaskeli && <span className="ml-1 font-mono">— kayıtlı: {mevcutMaskeli}</span>}
        </label>
        <input
          id="groq-anahtar"
          type="password"
          autoComplete="off"
          placeholder={mevcutMaskeli ? "Değiştirmek için yeni anahtar gir" : "Anahtarını yapıştır"}
          value={anahtar}
          onChange={(e) => setAnahtar(e.target.value)}
          className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm font-mono focus:border-foreground/25"
        />
      </div>
      {hata && <SonucMesaji ton="hata" mesaj={hata} />}
      {sonuc?.tur === "basarili" && <SonucMesaji ton="basarili" mesaj="Kaydedildi." />}
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => void kaydet()}
          disabled={kaydediliyor}
          className="rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:opacity-90 disabled:cursor-not-allowed disabled:bg-muted disabled:text-muted-foreground"
        >
          {kaydediliyor ? "Kaydediliyor…" : "Kaydet"}
        </button>
        <TestButonu saglayici="groq" />
      </div>
    </div>
  );
}

/** AI aracına bağlanma (MCP) — GET /settings/mcp'den ARAÇ BAŞINA parçacık + yol.

    #332: eskiden başlık birebir "Claude Code'a bağlan"dı ve tek bir yol
    (`<repo>/.mcp.json`) üretiyordu; oysa ürünün vaadi "HERKESİN aracı".
    Burada araç seçilir, yol/biçim ona göre değişir — özellikle **Codex TOML
    okur**, JSON parçacığını oraya yapıştırmak sessizce çalışmaz.

    DÜRÜSTLÜK (görev brifi, atlanamaz): backend bu bağlantıyı DOĞRULAYAMAZ —
    sahte "bağlandı ✓" durumu burada ASLA üretilmez, yalnız ne yapılması
    gerektiği söylenir. Bu uyarı kopyalama eylemine BAĞLI değil, HER ZAMAN
    görünür. */
function McpBolumu({ mcp }: { mcp: McpConfigSonucu | undefined }) {
  const [secili, setSecili] = useState<string | null>(null);
  const [kopyalandi, setKopyalandi] = useState(false);

  async function kopyala(metin: string) {
    try {
      await navigator.clipboard.writeText(metin);
      setKopyalandi(true);
      setTimeout(() => setKopyalandi(false), 2000);
    } catch {
      // Panoya erişim reddedilmiş olabilir (izin/tarayıcı desteği) — sessizce
      // yutulur AMA sahte "kopyalandı" da GÖSTERİLMEZ (aynı dürüstlük ilkesi:
      // yalnızca GERÇEKTEN olduysa söyle).
      setKopyalandi(false);
    }
  }

  return (
    <div className="space-y-3 rounded-lg border border-border bg-card p-4">
      <h2 className="text-sm font-semibold">AI aracına bağlan (MCP)</h2>
      {!mcp ? (
        <YuklemeIskeleti label="MCP yapılandırması yükleniyor" satir={1} />
      ) : mcp.tur === "yok" ? (
        <p className="text-xs text-muted-foreground">
          Bu sunucu sürümünde MCP ucu yok — güncelledikten sonra tekrar bak.
        </p>
      ) : mcp.tur === "beklenmeyen" ? (
        <HataDurumu baslik="MCP yapılandırması alınamıyor" hata={mcp.mesaj} />
      ) : (
        <McpReceteleri
          araclar={mcp.araclar}
          hostedNotu={mcp.hosted_notu}
          secili={secili ?? mcp.araclar[0]?.arac ?? null}
          onSec={(a) => {
            setSecili(a);
            setKopyalandi(false);
          }}
          kopyalandi={kopyalandi}
          onKopyala={kopyala}
        />
      )}
    </div>
  );
}

function McpReceteleri({
  araclar,
  hostedNotu,
  secili,
  onSec,
  kopyalandi,
  onKopyala,
}: {
  araclar: McpAracConfig[];
  hostedNotu: string | null;
  secili: string | null;
  onSec: (arac: string) => void;
  kopyalandi: boolean;
  onKopyala: (metin: string) => void | Promise<void>;
}) {
  const kayit = araclar.find((a) => a.arac === secili) ?? araclar[0];
  if (!kayit) return null;

  return (
    <>
      {/* Hosted: 404 yerine GEREKÇE (kabul kriteri) — "MCP yok" demek yerine
          neden yalnız yerelde çalıştığını ve ne yapılacağını söyler. */}
      {hostedNotu && (
        <p className="rounded-lg border border-status-in-review/40 bg-status-in-review/10 px-3 py-2 text-xs text-status-in-review">
          {hostedNotu}
        </p>
      )}

      <div role="group" aria-label="AI aracı seç" className="flex flex-wrap gap-1.5">
        {araclar.map((a) => (
          <button
            key={a.arac}
            type="button"
            aria-pressed={a.arac === kayit.arac}
            onClick={() => onSec(a.arac)}
            className={
              a.arac === kayit.arac
                ? "rounded-lg border border-foreground/25 bg-muted px-2.5 py-1 text-xs font-medium"
                : "rounded-lg border border-border px-2.5 py-1 text-xs text-muted-foreground hover:bg-muted/50"
            }
          >
            {a.ad}
          </button>
        ))}
      </div>

      <p className="text-xs text-muted-foreground">
        Aşağıdaki parçacığı şu dosyaya{" "}
        <strong>{kayit.paylasimli_dosya ? "EKLE (üzerine yazma)" : "yapıştır"}</strong>:
      </p>
      <p className="break-all rounded bg-muted px-2 py-1 font-mono text-xs">
        {kayit.yol}
        <span className="ml-2 rounded bg-background px-1.5 py-0.5 text-[10px] uppercase text-muted-foreground">
          {kayit.bicim}
        </span>
      </p>
      {/* Biçim uyarısı, dosya paylaşımlıysa: bu dosyada BAŞKA ayarlar da yaşar
          (Gemini CLI settings.json · Codex config.toml) — üzerine yazmak
          kullanıcının mevcut ayarlarını siler. */}
      {kayit.paylasimli_dosya && (
        <p className="rounded-lg border border-severity-high/40 bg-severity-high/10 px-3 py-2 text-xs text-severity-high">
          Bu dosyada başka ayarların da var — üzerine YAZMA, mevcut içeriğe ekle.
        </p>
      )}
      <pre className="overflow-x-auto rounded-lg border border-border bg-background p-3 text-xs">
        <code>{kayit.config_metni}</code>
      </pre>
      <button
        type="button"
        onClick={() => void onKopyala(kayit.config_metni)}
        className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium hover:bg-muted/50"
      >
        {kopyalandi ? "Kopyalandı ✓" : "Kopyala"}
      </button>
      <p className="text-xs text-muted-foreground">{kayit.aciklama}</p>
      <p className="rounded-lg border border-status-in-review/40 bg-status-in-review/10 px-3 py-2 text-xs text-status-in-review">
        Bu sayfa bağlantının kurulduğunu DOĞRULAYAMAZ — yapıştırdıktan sonra
        kendi aracında kontrol et. Sunucunun tek başına kalktığını görmek için:{" "}
        <span className="font-mono">make mcp</span>.
      </p>
      <p className="text-[11px] text-muted-foreground">
        Yol kaynağı:{" "}
        <a
          href={kayit.kaynak}
          target="_blank"
          rel="noreferrer"
          className="underline hover:text-foreground"
        >
          {kayit.ad} belgeleri
        </a>
      </p>
    </>
  );
}
