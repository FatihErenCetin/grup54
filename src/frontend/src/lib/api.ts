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

export const api = createClient<paths>({ baseUrl: config.apiBaseUrl });
