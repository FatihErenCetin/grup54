/**
 * Tipli API client (#20) — TEK GİRİŞ NOKTASI.
 * Kural: sayfalar fetch/axios'u DOĞRUDAN kullanmaz; yalnız bu client'tan geçer.
 * Tipler `src/api/schema.d.ts`'ten gelir — o dosya elle YAZILMAZ, backend'in
 * `src/shared/openapi.json`'undan üretilir (`npm run gen:api`); kontrat kayarsa
 * burası derlemede kırılır, CI drift-check'i de yakalar.
 */

import createClient from "openapi-fetch";
import type { paths } from "../api/schema.d.ts";
import { config } from "./config";

// Mock modu (#21): tek anahtar noktası burası — sayfalar mock'un varlığından
// habersizdir; canlıya geçiş = bayrağı kapatmak, silinecek sayfa kodu yok.
// DİKKAT — bilinçli config-istisnası: koşul import.meta.env üzerinden LİTERAL
// okunur ki Vite define-folding + DCE çalışsın; `config.mock` (obje property)
// üzerinden okununca Rollup dalı eleyemiyor ve fixture chunk'ı bayraksız
// build'de de deploy'a sızıyordu (adversarial doğrulama bulgusu — gerçek
// kullanıcı adları dist'e çıkıyordu). Bayrak semantiği yine config.ts'te
// doğrulanır (geçersiz değer açılışta hata).
const fetchImpl =
  import.meta.env.VITE_MOCK === "1"
    ? async (req: Request) => (await import("../mocks/radar")).mockFetch(req)
    : undefined;

export const api = createClient<paths>({ baseUrl: config.apiBaseUrl, fetch: fetchImpl });
