/**
 * Yerel sağlayıcı ayarları + Claude Code (MCP) bağlama — Ayarlar sayfasının
 * (T-309) veri katmanı. Backend T-307'de bitti ve merge edildi (#307/#308,
 * 945 test yeşil); burada YALNIZ tüketim var, `src/backend/**` bu görevde
 * DOKUNULMAZ.
 *
 * Sözleşme (kanonik: `api/routers/settings.py` modül dokümanı):
 *   GET  /settings/saglayici -> 200 {mode, saglayici, anahtarlar:{gemini,groq}, ollama_url} | 404
 *   PUT  /settings/saglayici    {saglayici, anahtar?, ollama_url?} -> 200 (aynı zarf) | 404 | 422
 *   POST /settings/test         {saglayici} -> 200 {calisiyor, mesaj} | 404 | 422
 *   GET  /settings/mcp       -> 200 {config_json, yol, mod, araclar[], hosted_notu}
 *
 * KURAL 1 (backend, settings.py): `ENSEMBLE_MODE != "local"` ise ANAHTAR uçları
 * (saglayici/test) 404 döner — frontend bunu "bu kurulumda ayarlar sayfası YOK"
 * olarak okur
 * (`tur: "yok"`). Bu, sayfanın/nav linkinin var olup olmayacağının TEK
 * doğruluk kaynağıdır — `config.mode` (Vite BUILD modu, #19) DEĞİL: prod
 * build'in kendisi hosted'da `ENSEMBLE_MODE=local` bir masaüstü paketiyle
 * (T-305/T-307 FAZ 3) servis edilebilir, gerçek kaynak her zaman backend'in
 * CANLI yanıtıdır (useAuth.ts'teki `enabled`/`emailEnabled` desenine simetrik).
 *
 * Dört fonksiyon da tipli `api` client'ından geçer, hiçbiri fırlatmaz — HTTP
 * durum kodu `tur` birleşimine eşlenir (useAuth.ts/useRepoSecici.ts kalıbının
 * AYNISI). openapi-fetch tuzağı: boş gövdeli yanıtta `error` `""` (falsy)
 * olabilir — bu yüzden HER YERDE `response.status`'a bakılır, `if (error)`
 * YAZILMAZ (`error === undefined || error === null` kontrolü kullanılır).
 */

import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import { backendMesaji } from "./useAuth";
import type { components } from "../api/schema.d.ts";

export type ProviderKeys = components["schemas"]["ProviderKeys"];
/** PUT/POST gövdesinin kabul ettiği üç değer — Groq DAHİL (yalnız GET/PUT'un
    "hangi slot güncelleniyor" seçimi; Groq'un `saglayici` alanının KENDİSİ,
    yani aktif sağlayıcı, olamayacağı ayrı bir kural — bkz. `saglayiciGuncelle`
    dosya-başı yorumu). */
export type SaglayiciTuru = components["schemas"]["ProviderTestRequest"]["saglayici"];
/** GET yanıtındaki `saglayici` — yalnız gemini|ollama (backend: Groq hiçbir
    zaman "aktif" olamaz, yalnız Gemini birincilken devreye giren bir yedek). */
export type AktifSaglayici = components["schemas"]["ProviderSettingsResponse"]["saglayici"];

export type SaglayiciAyarlari = {
  mode: "local" | "hosted";
  saglayici: AktifSaglayici;
  anahtarlar: ProviderKeys;
  ollama_url: string;
};

function veriyeCevir(
  data: components["schemas"]["ProviderSettingsResponse"],
): SaglayiciAyarlari {
  return {
    mode: data.mode,
    saglayici: data.saglayici,
    anahtarlar: data.anahtarlar,
    ollama_url: data.ollama_url,
  };
}

export type SaglayiciAyarlariSonucu =
  | ({ tur: "basarili" } & SaglayiciAyarlari)
  | { tur: "yok" } // 404 — bu kurulumda ayarlar sayfası yok (hosted)
  | { tur: "beklenmeyen"; mesaj: string };

/** GET /settings/saglayici — HTTP durum kodu → `tur` eşlemesinin KENDİSİ
    (ayarlarIstekleri.test.ts tarafından `api.GET` mock'lanarak doğrudan
    sınanır). `useSaglayiciAyarlari` bunu SARAR. */
export async function saglayiciAyarlariniGetir(): Promise<SaglayiciAyarlariSonucu> {
  try {
    const { data, error, response } = await api.GET("/settings/saglayici");
    if (error === undefined || error === null) {
      if (!data) return { tur: "beklenmeyen", mesaj: "Sunucu boş yanıt döndü." };
      return { tur: "basarili", ...veriyeCevir(data) };
    }
    if (response.status === 404) return { tur: "yok" };
    return {
      tur: "beklenmeyen",
      mesaj: backendMesaji(error, "Sağlayıcı ayarları alınamadı — az sonra tekrar dene."),
    };
  } catch (e) {
    return { tur: "beklenmeyen", mesaj: e instanceof Error ? e.message : "Sunucuya ulaşılamadı." };
  }
}

/** Ayarlar sayfasının GÖRÜNÜRLÜĞÜ (AppLayout nav linki) + sayfanın GÖVDESİ
    AYNI query key'i paylaşır (`["settings","saglayici"]`) — react-query aynı
    render ağacında tek istekte tekilleştirir, iki kez fetch atılmaz.
    `refetchOnWindowFocus: false` (useRepolar'ın AKSİNE, o kasıtlı `true`):
    `ENSEMBLE_MODE` sunucu süreci ayaktayken DEĞİŞMEYEN bir sunucu ayarı —
    kullanıcı sekmeye geri döndüğünde tekrar sormanın hiçbir faydası yok. */
export function useSaglayiciAyarlari() {
  return useQuery({
    queryKey: ["settings", "saglayici"],
    queryFn: saglayiciAyarlariniGetir,
    retry: false,
    refetchOnWindowFocus: false,
  });
}

export type SaglayiciGuncelleSonucu =
  | ({ tur: "basarili" } & SaglayiciAyarlari)
  | { tur: "yok" } // 404
  | { tur: "gecersiz"; mesaj: string } // 422 (örn. geçersiz Ollama URL'i)
  | { tur: "beklenmeyen"; mesaj: string };

/** PUT /settings/saglayici — `saglayici` HANGİ slotun güncellendiğini seçer.
    Backend `saglayici` "gemini"/"ollama" ise AYNI ZAMANDA aktif sağlayıcıyı
    da BUNA çevirir (radio-button semantiği, `anahtar`/`ollama_url` boş
    geçilse BİLE — bkz. settings.py: `if payload.saglayici in ("gemini",
    "ollama"): data["llm_provider"] = payload.saglayici`, KOŞULSUZ). `saglayici:
    "groq"` ise yalnız yedek anahtarı günceller, aktif sağlayıcıyı ASLA
    değiştirmez.

    `anahtar`/`ollama_url` boş bırakılırsa (undefined) mevcut değer KORUNUR —
    çağıran (AyarlarPage) boş input'u undefined'a çevirir; maskelenmiş değeri
    (`ANAH…4f2c`) buraya geri göndermek gerçek anahtarı BOZARDI. */
export async function saglayiciGuncelle(payload: {
  saglayici: SaglayiciTuru;
  anahtar?: string;
  ollama_url?: string;
}): Promise<SaglayiciGuncelleSonucu> {
  try {
    const { data, error, response } = await api.PUT("/settings/saglayici", { body: payload });
    if (error === undefined || error === null) {
      if (!data) return { tur: "beklenmeyen", mesaj: "Sunucu boş yanıt döndü." };
      return { tur: "basarili", ...veriyeCevir(data) };
    }
    switch (response.status) {
      case 404:
        return { tur: "yok" };
      case 422:
        return { tur: "gecersiz", mesaj: backendMesaji(error, "Girdi geçersiz — kontrol et.") };
      default:
        return {
          tur: "beklenmeyen",
          mesaj: backendMesaji(error, "Kaydedilemedi — az sonra tekrar dene."),
        };
    }
  } catch (e) {
    return { tur: "beklenmeyen", mesaj: e instanceof Error ? e.message : "Sunucuya ulaşılamadı." };
  }
}

export type SaglayiciTestSonucu =
  | { tur: "sonuc"; calisiyor: boolean; mesaj: string } // 200 — backend'in GERÇEK sonucu; calisiyor:false BİR HATA DEĞİL, dürüst bir "çalışmıyor" bulgusu
  | { tur: "yok" } // 404
  | { tur: "gecersiz"; mesaj: string } // 422
  | { tur: "beklenmeyen"; mesaj: string };

/** POST /settings/test — GERÇEK bir ağ çağrısı (backend docstring'i: liste/
    metadata ucu, üretim kotasını yakmaz). Kendi başarı/başarısızlık mesajını
    UYDURMAZ — `calisiyor`/`mesaj` AYNEN backend'den gelir (görev brifi
    "kendi başarı mesajını UYDURMA"). */
export async function saglayiciTestEt(saglayici: SaglayiciTuru): Promise<SaglayiciTestSonucu> {
  try {
    const { data, error, response } = await api.POST("/settings/test", {
      body: { saglayici },
    });
    if (error === undefined || error === null) {
      if (!data) return { tur: "beklenmeyen", mesaj: "Sunucu boş yanıt döndü." };
      return { tur: "sonuc", calisiyor: data.calisiyor, mesaj: data.mesaj };
    }
    switch (response.status) {
      case 404:
        return { tur: "yok" };
      case 422:
        return { tur: "gecersiz", mesaj: backendMesaji(error, "Girdi geçersiz — kontrol et.") };
      default:
        return {
          tur: "beklenmeyen",
          mesaj: backendMesaji(error, "Test edilemedi — az sonra tekrar dene."),
        };
    }
  } catch (e) {
    return { tur: "beklenmeyen", mesaj: e instanceof Error ? e.message : "Sunucuya ulaşılamadı." };
  }
}

/** Araç başına bağlanma reçetesi (#332) — `bicim` kritik: Codex TOML okur,
    diğer dördü JSON; aynı parçacığı hepsine vermek SESSİZCE çalışmaz. */
export type McpAracConfig = components["schemas"]["McpAracConfig"];

export type McpConfigSonucu =
  | {
      tur: "basarili";
      config_json: string;
      yol: string;
      mod: "local" | "hosted";
      araclar: McpAracConfig[];
      hosted_notu: string | null;
    }
  | { tur: "yok" } // 404 — bu sürümde uç yok (eski backend)
  | { tur: "beklenmeyen"; mesaj: string };

/** GET /settings/mcp — araç başına hazır parçacık + hedef yol. Sahte
    "bağlandı" durumu YOK (backend docstring'i) — bu fonksiyon da İCAT ETMEZ,
    yalnız içerik + yol taşır; "bağlantı kuruldu mu" sorusuna sayfa HİÇBİR
    ZAMAN evet demez (görev brifi §DÜRÜSTLÜK).

    #332: bu uç hosted'da ARTIK 404 değil — `mod: "hosted"` + `hosted_notu`
    (MCP'nin neden yalnız yerel bir stdio süreciyle çalıştığı) döner. `"yok"`
    dalı yine de duruyor: uç eklenmeden önceki bir backend'e karşı çalışan
    frontend sessizce çökmesin. */
export async function mcpConfigGetir(): Promise<McpConfigSonucu> {
  try {
    const { data, error, response } = await api.GET("/settings/mcp");
    if (error === undefined || error === null) {
      if (!data) return { tur: "beklenmeyen", mesaj: "Sunucu boş yanıt döndü." };
      return {
        tur: "basarili",
        config_json: data.config_json,
        yol: data.yol,
        mod: data.mod,
        araclar: data.araclar,
        hosted_notu: data.hosted_notu ?? null,
      };
    }
    if (response.status === 404) return { tur: "yok" };
    return {
      tur: "beklenmeyen",
      mesaj: backendMesaji(error, "MCP yapılandırması alınamadı — az sonra tekrar dene."),
    };
  } catch (e) {
    return { tur: "beklenmeyen", mesaj: e instanceof Error ? e.message : "Sunucuya ulaşılamadı." };
  }
}

/** Polling YOK (useKurulumlar'ın aynı ilkesi) — `.mcp.json` içeriği repo kökü
    değişmedikçe sabittir, 10 sn'de bir sorulacak bir şey değil. */
export function useMcpConfig(enabled: boolean) {
  return useQuery({
    queryKey: ["settings", "mcp"],
    queryFn: mcpConfigGetir,
    enabled,
    retry: false,
    refetchOnWindowFocus: false,
  });
}
