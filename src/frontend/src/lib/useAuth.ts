/**
 * Auth durumu (#79) — opsiyonel GitHub OAuth + (T-294/D-57) opsiyonel
 * email+parola üyeliği. İKİ AYRI KAPI, birbirinden bağımsız (bkz.
 * `.harness/decisions/D-57-email-parola-uyeligi.md` + `api/routers/auth.py`
 * modül dokümanı): `enabled` = GitHub OAuth yapılandırılmış mı, `emailEnabled`
 * = email üyeliği açık mı. Bir kullanıcı ikisinden BİRİYLE (ya da GitHub
 * kapalıyken yalnız email'le) oturum açmış olabilir — bu yüzden `/auth/me`
 * `enabled || emailEnabled` iken çağrılır, yalnız `enabled` iken DEĞİL.
 *
 * DİKKAT — bilinçli sapma (hâlâ ham `fetch`, tipli client DEĞİL): `/auth/config`
 * + `/auth/me` + `/auth/logout` bu dosyada halihazırda ham `fetch` ile
 * yazılmıştı (schema henüz yokken); şema artık üretildi ama BU üç ucun
 * çağrı şeklini T-294 kapsamında DEĞİŞTİRMİYORUZ — mevcut testler
 * (`tests/auth.test.tsx`) tam olarak bu ham-fetch sözleşmesini kilitliyor,
 * gereksiz bir migrasyon onları kırardı. YENİ eklenen `/auth/register` +
 * `/auth/login` ise (aşağıda) tipli `api` client'ından geçer — "sayfalar
 * fetch'i doğrudan kullanmaz" kuralı üretilmiş kontrata giren uçlar için tam
 * uygulanır (görev brifi: "üretilmiş client üzerinden çağır, elle tip yazma").
 *
 * Sözleşme (kanonik: `api/routers/auth.py` modül dokümanı):
 *   GET  /auth/config -> 200 {enabled, email_enabled: bool}      HER ZAMAN 200
 *   GET  /auth/me      -> 200 {handle, avatar_url, email: str|null} | 401
 *                          (401 = anonim, bu HATA DEĞİL; handle/email en az
 *                          biri dolu — GitHub oturumunda handle, email
 *                          oturumunda email dolu)
 *   POST /auth/register -> 201 + oturum çerezi | 409/422/429/503
 *   POST /auth/login    -> 200 + oturum çerezi | 401/422/429/503
 *   POST /auth/logout  -> 204, çerezi siler
 *
 * Çerez `credentials: "include"` ile taşınır (imzalı/HttpOnly oturum çerezi).
 */

import { useEffect, useState } from "react";
import { api } from "./api";
import { config } from "./config";
import type { components } from "../api/schema.d.ts";

type AuthUserResponse = components["schemas"]["AuthUserResponse"];

/** `handle` VE `email` artık ikisi de opsiyonel (T-294): GitHub oturumunda
    handle dolu/email null, email oturumunda tam tersi — en az biri dolu olmalı. */
export type AuthKullanici = {
  handle: string | null;
  avatar_url: string | null;
  email: string | null;
};

export type AuthDurumu = {
  /** Bu kurulumda GitHub girişi yapılandırılmış mı (sırlar yoksa false). */
  enabled: boolean;
  /** Bu kurulumda email+parola üyeliği açık mı (T-294/D-57). */
  emailEnabled: boolean;
  /** Giriş yapılmışsa kullanıcı; anonimse (ya da iki kapı da kapalıysa) null. */
  kullanici: AuthKullanici | null;
  isLoading: boolean;
  /** GERÇEK hata (config/me çağrısı başarısız oldu) — 401 burada YER ALMAZ,
      401 anonim demektir, hata değildir. */
  error: unknown;
};

async function getJSON(yol: string): Promise<{ status: number; govde: unknown }> {
  const res = await fetch(`${config.apiBaseUrl}${yol}`, { credentials: "include" });
  let govde: unknown;
  try {
    govde = await res.json();
  } catch {
    // Boş gövde (örn. bazı 401 yanıtları) — govde undefined kalır, hata değil.
    govde = undefined;
  }
  return { status: res.status, govde };
}

const BASLANGIC: AuthDurumu = {
  enabled: false,
  emailEnabled: false,
  kullanici: null,
  isLoading: true,
  error: null,
};

export function useAuth(): AuthDurumu {
  const [durum, setDurum] = useState<AuthDurumu>(BASLANGIC);

  useEffect(() => {
    let iptal = false;

    async function yukle() {
      try {
        // Sözleşme: /auth/config HER ZAMAN 200 döner — farklısı gerçek hata.
        const { status: configStatus, govde: configGovde } = await getJSON("/auth/config");
        if (configStatus !== 200) {
          throw new Error(`/auth/config beklenmeyen durum kodu: ${configStatus}`);
        }
        const o = configGovde as { enabled?: unknown; email_enabled?: unknown } | undefined;
        const enabled = o?.enabled === true;
        const emailEnabled = o?.email_enabled === true;
        if (iptal) return;

        // İkisi de kapalıysa /auth/me'ye HİÇ gidilmez (boşuna istek atma) —
        // T-294 öncesi yalnız `enabled`e bakıyordu; artık email-only oturumlar
        // da mümkün olduğu için `emailEnabled` de KOŞULA girer.
        if (!enabled && !emailEnabled) {
          setDurum({
            enabled: false,
            emailEnabled: false,
            kullanici: null,
            isLoading: false,
            error: null,
          });
          return;
        }

        const { status: meStatus, govde: meGovde } = await getJSON("/auth/me");
        if (meStatus === 401) {
          // Anonim — HATA DEĞİL (sözleşme). Konsola basma, kırmızı kutu yok.
          if (!iptal) {
            setDurum({ enabled, emailEnabled, kullanici: null, isLoading: false, error: null });
          }
          return;
        }
        if (meStatus !== 200) {
          throw new Error(`/auth/me beklenmeyen durum kodu: ${meStatus}`);
        }
        const m = meGovde as
          | { handle?: unknown; avatar_url?: unknown; email?: unknown }
          | undefined;
        const handle = typeof m?.handle === "string" && m.handle !== "" ? m.handle : null;
        const email = typeof m?.email === "string" && m.email !== "" ? m.email : null;
        // T-294: `handle` VE `email` ikisi de opsiyonel — ama İKİSİ DE eksikse
        // (ne GitHub ne email kimliği) bu gövde bozuk demektir, sessizce
        // yutulmaz (eski davranış: yalnız handle zorunluydu).
        if (handle === null && email === null) {
          throw new Error("/auth/me: handle/email alanlarının ikisi de eksik/geçersiz");
        }
        if (!iptal) {
          setDurum({
            enabled,
            emailEnabled,
            kullanici: {
              handle,
              email,
              avatar_url: typeof m?.avatar_url === "string" ? m.avatar_url : null,
            },
            isLoading: false,
            error: null,
          });
        }
      } catch (e) {
        if (!iptal) {
          setDurum({
            enabled: false,
            emailEnabled: false,
            kullanici: null,
            isLoading: false,
            error: e,
          });
        }
      }
    }

    void yukle();
    return () => {
      iptal = true;
    };
  }, []);

  return durum;
}

/** Kullanıcının görünen adı: GitHub handle'ı varsa o, yoksa email — ikisi de
    yoksa (teorik olarak olmamalı, bkz. useAuth doğrulaması) sabit bir yer
    tutucu. ActorChip/AuthGostergesi gibi tek-string bekleyen yerlerde ortak
    kullanılsın diye TEK yerde (drift olmasın). */
export function gorunenAd(kullanici: AuthKullanici): string {
  return kullanici.handle ?? kullanici.email ?? "kullanıcı";
}

/** POST /auth/logout — çerezi siler (204'ten farklısı gerçek hata). */
async function cikisIstegiGonder(): Promise<void> {
  const res = await fetch(`${config.apiBaseUrl}/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
  if (res.status !== 204) {
    throw new Error(`/auth/logout beklenmeyen durum kodu: ${res.status}`);
  }
}

/** Çıkış aksiyonu + durumu — header göstergesi ve LoginPage arasında ortak.
    Sahte-canlılık yasak (D-34): başarıyla çıkış sonrası state iyimser
    sıfırlanmaz, tam sayfa yeniden yüklenip GERÇEK anonim durum sunucudan
    tazelenir (useAuth zaten mount'ta /auth/config + /auth/me'yi tekrar sorar). */
export function useCikisYap() {
  const [yukleniyor, setYukleniyor] = useState(false);
  const [hata, setHata] = useState<unknown>(null);

  async function cikisYap() {
    setYukleniyor(true);
    setHata(null);
    try {
      await cikisIstegiGonder();
      window.location.reload();
    } catch (e) {
      setYukleniyor(false);
      setHata(e);
    }
  }

  return { cikisYap, yukleniyor, hata };
}

/* ── Email + parola üyeliği (T-294/D-57) ─────────────────────────────────────
   register/login BURADAN itibaren tipli `api` client'ından geçer (üretilmiş
   kontrata giren yeni uçlar — "elle tip yazma" kuralı burada tam uygulanır).
   `/auth/config` + `/auth/me` + `/auth/logout` bilinçle ham fetch'te KALDI
   (yukarıdaki dosya-başı notu). */

function authUserToKullanici(o: AuthUserResponse): AuthKullanici {
  return {
    handle: o.handle ?? null,
    avatar_url: o.avatar_url ?? null,
    email: o.email ?? null,
  };
}

/** 429 yanıtının `Retry-After` başlığından saniye okur — uydurma sayı YOK
    (başlık yoksa/ayrıştırılamazsa `null`, çağıran genel bir mesaja düşer). */
function retryAfterSaniye(response: Response): number | null {
  const ham = response.headers.get("Retry-After");
  if (!ham) return null;
  const n = Number(ham);
  return Number.isFinite(n) && n > 0 ? n : null;
}

/** Backend'in ErrorEnvelope'ından ({error,message,status} — api/errors.py)
    insan-okur mesajı çıkarır; yoksa YEDEK metne düşer (uydurma değil, gerçek
    bir bağlam kaybı durumunda dürüst bir varsayılan). openapi-fetch bazı
    durumlarda (409/422/429 register — şemada `content?: never` beyanlı, ama
    runtime'da backend HER ZAMAN bu zarfı döner, bkz. api/routers/auth.py +
    api/errors.py::http_exception) `error` alanının statik tipini yakalayamaz
    — bu yüzden burada `unknown` üzerinden GÜVENLİ biçimde okunur.

    `export`: T-79 repo seçici (`useRepoSecici.ts`) install-url/installations/
    repos uçlarının 403/503 zarfları için AYNI çıkarımı kullanır — iki ayrı
    kopya iki farklı "uydurma yedek metin" riski taşırdı (TDK ilkesi). */
export function backendMesaji(hata: unknown, yedek: string): string {
  if (hata !== null && typeof hata === "object") {
    const m = (hata as { message?: unknown }).message;
    if (typeof m === "string" && m !== "") return m;
  }
  return yedek;
}

/** register/login ortak sonuç sözleşmesi — sayfa yalnız `tur`a göre dallanır,
    `mesaj` HER ZAMAN backend'in kendi (ya da dürüst bir yedek) TR metnidir;
    kendi mesajını UYDURMAZ (görev brifi kuralı). */
export type AuthEylemSonucu =
  | { tur: "basarili"; kullanici: AuthKullanici }
  | { tur: "email_kayitli"; mesaj: string } // register 409
  | { tur: "gecersiz_giris"; mesaj: string } // login 401 — GENEL, ayrım YOK
  | { tur: "politika_ihlali"; mesaj: string } // register/login 422
  | { tur: "cok_fazla_deneme"; mesaj: string; saniye: number | null } // 429
  | { tur: "kapali"; mesaj: string } // 503 — email üyeliği yapılandırılmamış
  | { tur: "beklenmeyen"; mesaj: string }; // diğer HTTP durumları + ağ hatası

/** POST /auth/register — 201 + oturum çerezi | 409/422/429/503. */
export async function kayitOlIstegi(email: string, password: string): Promise<AuthEylemSonucu> {
  try {
    const { data, error, response } = await api.POST("/auth/register", {
      body: { email, password },
    });
    if (error === undefined || error === null) {
      if (!data) return { tur: "beklenmeyen", mesaj: "Sunucu boş yanıt döndü." };
      return { tur: "basarili", kullanici: authUserToKullanici(data) };
    }
    switch (response.status) {
      case 409:
        return { tur: "email_kayitli", mesaj: backendMesaji(error, "Bu e-posta zaten kayıtlı.") };
      case 422:
        return {
          tur: "politika_ihlali",
          mesaj: backendMesaji(error, "Parola politikası ya da e-posta biçimi geçersiz."),
        };
      case 429:
        return {
          tur: "cok_fazla_deneme",
          mesaj: backendMesaji(error, "Çok fazla deneme yapıldı — birazdan tekrar deneyin."),
          saniye: retryAfterSaniye(response),
        };
      case 503:
        return {
          tur: "kapali",
          mesaj: backendMesaji(error, "E-posta ile üyelik şu anda kullanılamıyor."),
        };
      default:
        return {
          tur: "beklenmeyen",
          mesaj: backendMesaji(error, "Kayıt tamamlanamadı — az sonra tekrar dene."),
        };
    }
  } catch (e) {
    return { tur: "beklenmeyen", mesaj: e instanceof Error ? e.message : "Sunucuya ulaşılamadı." };
  }
}

/** POST /auth/login — 200 + oturum çerezi | 401/422/429/503.
    401 KOŞULSUZ genel mesaj taşır (backend "e-posta bulunamadı" ile "parola
    yanlış"ı AYIRMAZ — kullanıcı-sayımı savunması, D-57/#294 madde 6); burada
    da başka bir ayrım İCAT EDİLMEZ, backend'in genel metni AYNEN gösterilir. */
export async function girisYapIstegi(email: string, password: string): Promise<AuthEylemSonucu> {
  try {
    const { data, error, response } = await api.POST("/auth/login", {
      body: { email, password },
    });
    if (error === undefined || error === null) {
      if (!data) return { tur: "beklenmeyen", mesaj: "Sunucu boş yanıt döndü." };
      return { tur: "basarili", kullanici: authUserToKullanici(data) };
    }
    switch (response.status) {
      case 401:
        return {
          tur: "gecersiz_giris",
          mesaj: backendMesaji(error, "E-posta ya da parola hatalı."),
        };
      case 422:
        return {
          tur: "politika_ihlali",
          mesaj: backendMesaji(error, "Girdi geçersiz — e-posta/parolayı kontrol et."),
        };
      case 429:
        return {
          tur: "cok_fazla_deneme",
          mesaj: backendMesaji(error, "Çok fazla deneme yapıldı — birazdan tekrar deneyin."),
          saniye: retryAfterSaniye(response),
        };
      case 503:
        return {
          tur: "kapali",
          mesaj: backendMesaji(error, "E-posta ile giriş şu anda kullanılamıyor."),
        };
      default:
        return {
          tur: "beklenmeyen",
          mesaj: backendMesaji(error, "Giriş tamamlanamadı — az sonra tekrar dene."),
        };
    }
  } catch (e) {
    return { tur: "beklenmeyen", mesaj: e instanceof Error ? e.message : "Sunucuya ulaşılamadı." };
  }
}
