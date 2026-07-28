/**
 * Repo seçici (#79 — çok-kiracılı yarısının arayüzü, T-79'un kalan dilimi).
 * Kullanıcının GitHub App kurulumları + izlediği/aktif repo seçimi.
 *
 * Sözleşme (kanonik: `api/routers/auth.py` modül dokümanı, brifing birebir):
 *   GET  /auth/install-url    -> 200 {url}                       | 401 | 503 (App yapılandırılmamış)
 *   GET  /auth/installations  -> 200 {installations: [...]}      | 401 | 503
 *   GET  /auth/repos          -> 200 {selected, active, demo}    | 401
 *   PUT  /auth/repos          {repos, active} -> 200 {selected, active} | 401 | 403 (izinsiz repo)
 *
 * Dördü de tipli `api` client'ından geçer (üretilmiş kontrat) — useAuth.ts'teki
 * kayitOlIstegi/girisYapIstegi kalıbının AYNISI: hiçbiri fırlatmaz, HTTP durum
 * kodu -> "tur" birleşimine eşlenir; çağıran yalnız `tur`a göre dallanır. Bu
 * fonksiyonlar `unknown` gövdeli hatayı asla ekrana çıplak basmaz — backend'in
 * KENDİ mesajı (`backendMesaji`, useAuth.ts) ya da dürüst bir yedek metin.
 *
 * `giris_gerekli` (401): bu uçlara normalde yalnız RepoSeciciPage'in ÜSTTEKİ
 * `useAuth` kapısını geçmiş (oturumlu) kullanıcılar ulaşır — ama oturum ARADA
 * sona erebilir (çerez süresi, başka sekmede çıkış). Her fonksiyon KENDİ
 * 401'ini de taşır ki sayfa bunu da /login'e yönlendirmeye çevirebilsin;
 * "zaten girişliydi" varsayımıyla sessizce yutulmaz.
 *
 * 403 (yalnız `repolariGuncelle`): backend'in "istemcinin gönderdiği repo'ya
 * asla körlemesine güvenilmez" ilkesinin GÖRÜNÜR YÜZÜ — UI yalnız CANLI
 * kurulum listesinden seçim sunduğu için normal akışta oluşmaz, ama kurulum
 * listesi değiştiği (repo App'ten kaldırıldı) arada bir yarış penceresinde
 * mümkündür. Backend'in mesajı AYNEN gösterilir, kendi ayrımı İCAT EDİLMEZ.
 */

import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import { backendMesaji } from "./useAuth";
import type { components } from "../api/schema.d.ts";

export type KurulumOzeti = components["schemas"]["InstallationSummary"];
export type RepoOzeti = components["schemas"]["RepoSummary"];

export type KurulumUrlSonucu =
  | { tur: "basarili"; url: string }
  | { tur: "giris_gerekli" } // 401
  | { tur: "kapali"; mesaj: string } // 503 — GitHub App kurulum akışı yapılandırılmamış
  | { tur: "beklenmeyen"; mesaj: string };

/** GET /auth/install-url — "GitHub App'i kur" eylemi bu adresi ANLIK ister,
    sonra tarayıcıyı ORAYA yönlendirir (bu uç kendisi bir redirect DEĞİL,
    `/auth/login`'in aksine düz JSON döner — çağıran `window.location.href`
    atamalı). */
export async function kurulumUrlIstegi(): Promise<KurulumUrlSonucu> {
  try {
    const { data, error, response } = await api.GET("/auth/install-url");
    if (error === undefined || error === null) {
      if (!data?.url) return { tur: "beklenmeyen", mesaj: "Sunucu boş yanıt döndü." };
      return { tur: "basarili", url: data.url };
    }
    switch (response.status) {
      case 401:
        return { tur: "giris_gerekli" };
      case 503:
        return {
          tur: "kapali",
          mesaj: backendMesaji(
            error,
            "GitHub App kurulum akışı bu kurulumda yapılandırılmamış.",
          ),
        };
      default:
        return {
          tur: "beklenmeyen",
          mesaj: backendMesaji(error, "Kurulum adresi alınamadı — az sonra tekrar dene."),
        };
    }
  } catch (e) {
    return { tur: "beklenmeyen", mesaj: e instanceof Error ? e.message : "Sunucuya ulaşılamadı." };
  }
}

export type KurulumlarSonucu =
  | { tur: "basarili"; installations: KurulumOzeti[] }
  | { tur: "giris_gerekli" } // 401
  | { tur: "kapali"; mesaj: string } // 503 — GitHub App entegrasyonu yapılandırılmamış
  | { tur: "beklenmeyen"; mesaj: string };

/** `export`: HTTP durum kodu → `tur` eşlemesinin KENDİSİ (repoSeciciIstekleri.test.ts
    tarafından `api.GET` mock'lanarak doğrudan sınanır) — authIstekleri.test.ts'teki
    kayitOlIstegi/girisYapIstegi kalıbının aynısı; `useKurulumlar` bunu SARAR. */
export async function kurulumlariGetir(): Promise<KurulumlarSonucu> {
  try {
    const { data, error, response } = await api.GET("/auth/installations");
    if (error === undefined || error === null) {
      return { tur: "basarili", installations: data?.installations ?? [] };
    }
    switch (response.status) {
      case 401:
        return { tur: "giris_gerekli" };
      case 503:
        return {
          tur: "kapali",
          mesaj: backendMesaji(
            error,
            "GitHub App entegrasyonu bu kurulumda yapılandırılmamış.",
          ),
        };
      default:
        return {
          tur: "beklenmeyen",
          mesaj: backendMesaji(error, "Kurulumlar alınamadı — az sonra tekrar dene."),
        };
    }
  } catch (e) {
    return { tur: "beklenmeyen", mesaj: e instanceof Error ? e.message : "Sunucuya ulaşılamadı." };
  }
}

/** Polling YOK (bilinçli — usePolling.ts'in "tek-atış uç" dalı gibi): kurulum
    listesi kullanıcı GitHub'a gidip App kurduğunda değişir, 10 sn'de bir
    kendiliğinden değil. `enabled=false` iken (örn. henüz oturum doğrulanmadı)
    hiç istek atılmaz — useAuth.ts'teki "boşuna istek atma" ilkesi. */
export function useKurulumlar(enabled: boolean) {
  return useQuery({
    queryKey: ["auth", "installations"],
    queryFn: kurulumlariGetir,
    enabled,
    refetchOnWindowFocus: true,
    retry: false,
  });
}

export type ReposSonucu =
  | { tur: "basarili"; selected: string[]; active: string | null; demo: string | null }
  | { tur: "giris_gerekli" } // 401
  | { tur: "beklenmeyen"; mesaj: string };

export async function repolariGetir(): Promise<ReposSonucu> {
  try {
    const { data, error, response } = await api.GET("/auth/repos");
    if (error === undefined || error === null) {
      return {
        tur: "basarili",
        selected: data?.selected ?? [],
        active: data?.active ?? null,
        demo: data?.demo ?? null,
      };
    }
    switch (response.status) {
      case 401:
        return { tur: "giris_gerekli" };
      default:
        return {
          tur: "beklenmeyen",
          mesaj: backendMesaji(error, "Repo bilgisi alınamadı — az sonra tekrar dene."),
        };
    }
  } catch (e) {
    return { tur: "beklenmeyen", mesaj: e instanceof Error ? e.message : "Sunucuya ulaşılamadı." };
  }
}

export function useRepolar(enabled: boolean) {
  return useQuery({
    queryKey: ["auth", "repos"],
    queryFn: repolariGetir,
    enabled,
    refetchOnWindowFocus: true,
    retry: false,
  });
}

export type ReposGuncelleSonucu =
  | { tur: "basarili"; selected: string[]; active: string | null }
  | { tur: "giris_gerekli" } // 401
  | { tur: "izinsiz"; mesaj: string } // 403 — backend'in "erişimin yok" mesajı
  | { tur: "beklenmeyen"; mesaj: string };

/** PUT /auth/repos — `repos`: kullanıcının izlemek istediği tam liste (var
    olan seçimin YERİNE geçer, artımlı değil — backend sözleşmesi böyle).
    `active`: bu isteğin ARDINDAN hangi repo "şu an baktığım" olsun; `null` =
    demo reposuna dön (backend `active_repo_full_name=None` iken otomatik
    demo'ya düşer, bkz. `api/deps.py::get_tenant`). */
export async function repolariGuncelle(
  repos: string[],
  active: string | null,
): Promise<ReposGuncelleSonucu> {
  try {
    const { data, error, response } = await api.PUT("/auth/repos", {
      body: { repos, active },
    });
    if (error === undefined || error === null) {
      if (!data) return { tur: "beklenmeyen", mesaj: "Sunucu boş yanıt döndü." };
      return { tur: "basarili", selected: data.selected, active: data.active ?? null };
    }
    switch (response.status) {
      case 401:
        return { tur: "giris_gerekli" };
      case 403:
        return {
          tur: "izinsiz",
          mesaj: backendMesaji(error, "Bu repolara erişiminiz yok."),
        };
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
