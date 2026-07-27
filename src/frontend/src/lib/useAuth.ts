/**
 * Auth durumu (#79) — opsiyonel GitHub OAuth.
 *
 * DİKKAT — geçici ham `fetch`: bu görevin yazıldığı sırada `/auth/*` uçları
 * `src/shared/openapi.json`da (dolayısıyla üretilen `api/schema.d.ts`ta) henüz
 * YOK — AUTH SÖZLEŞMESİ önce tanımlandı, backend paralelde yazıyor. Şema
 * `make contracts` ile yenilenince (doğrulama aşaması) bu dosya tipli `api`
 * client'ına (openapi-fetch) taşınmalı; o güne kadarki bilinçli sapma —
 * "sayfalar fetch'i doğrudan kullanmaz" kuralı üretilmiş kontrata giren uçlar
 * içindir, henüz üretilmemiş bir uç için değil.
 *
 * Sözleşme (görev brifi — iki taraf da buna göre yazar, uydurma yok):
 *   GET  /auth/config -> 200 {enabled: bool}                    HER ZAMAN 200
 *   GET  /auth/me      -> 200 {handle, avatar_url: str|null} | 401
 *                          (401 = anonim, bu HATA DEĞİL)
 *   POST /auth/logout  -> 204, çerezi siler
 *
 * Çerez `credentials: "include"` ile taşınır (imzalı/HttpOnly oturum çerezi —
 * bkz. görev brifi "AUTH SÖZLEŞMESİ" çerez notu).
 */

import { useEffect, useState } from "react";
import { config } from "./config";

export type AuthKullanici = { handle: string; avatar_url: string | null };

export type AuthDurumu = {
  /** Bu kurulumda GitHub girişi yapılandırılmış mı (sırlar yoksa false). */
  enabled: boolean;
  /** Giriş yapılmışsa kullanıcı; anonimse (ya da enabled=false ise) null. */
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
        const enabled = (configGovde as { enabled?: unknown } | undefined)?.enabled === true;
        if (iptal) return;

        if (!enabled) {
          setDurum({ enabled: false, kullanici: null, isLoading: false, error: null });
          return;
        }

        const { status: meStatus, govde: meGovde } = await getJSON("/auth/me");
        if (meStatus === 401) {
          // Anonim — HATA DEĞİL (sözleşme). Konsola basma, kırmızı kutu yok.
          if (!iptal) {
            setDurum({ enabled: true, kullanici: null, isLoading: false, error: null });
          }
          return;
        }
        if (meStatus !== 200) {
          throw new Error(`/auth/me beklenmeyen durum kodu: ${meStatus}`);
        }
        const o = meGovde as { handle?: unknown; avatar_url?: unknown } | undefined;
        if (typeof o?.handle !== "string" || o.handle === "") {
          throw new Error("/auth/me: handle alanı eksik/geçersiz");
        }
        if (!iptal) {
          setDurum({
            enabled: true,
            kullanici: {
              handle: o.handle,
              avatar_url: typeof o.avatar_url === "string" ? o.avatar_url : null,
            },
            isLoading: false,
            error: null,
          });
        }
      } catch (e) {
        if (!iptal) {
          setDurum({ enabled: false, kullanici: null, isLoading: false, error: e });
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
