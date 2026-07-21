#!/usr/bin/env node
/**
 * #188 — Prod build hijyen guard: `npm run build` bittikten SONRA `dist/`'i
 * tarar. Üç kategori bulunursa exit 1 (CI kırmızı):
 *
 *   1. Bilinen mock fixture bayrakları (mockFetch / mocks/radar) — VITE_MOCK
 *      gate'i DCE'yi eleyemedi, mock kod prod'a sızdı (#21 bulgusunun aynısı).
 *   2. Bilinen fixture handle'ları — gerçek/eski kişi adları dist'e sızdı
 *      (bu issue'nun "Neden"i: asmarufoglu/EnesErdemT/fatih-claude sızmıştı).
 *   3. Backend sır imzaları — GEMINI_ / GITHUB_ / DATABASE_URL ya da PEM
 *      başlığı frontend bundle'ında ASLA olmamalı (frontend yalnız VITE_
 *      önekli değişkenleri okur, #19).
 *
 * Kaynak: bu liste tek elden `src/frontend/src/mocks/*.ts` + bilinen geçmiş
 * sızıntı vakalarından derlenir; yeni bir fixture handle'ı eklenince buraya
 * da eklenmesi gerekir (frozen değil, kasıtlı elle-senkron — az sayıda kayıt).
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const DIST_DIR = process.argv[2] ?? "dist";

// Yalnızca metin olarak taranabilir uzantılar (binary asset'leri atla).
const SCANNABLE_EXTENSIONS = new Set([".js", ".mjs", ".cjs", ".html", ".css", ".json", ".map"]);

const MOCK_FLAG_MARKERS = [
  { label: "mockFetch (VITE_MOCK fixture fonksiyonu)", pattern: "mockFetch" },
  { label: "mocks/radar (radar fixture modülü)", pattern: "mocks/radar" },
];

// #188 "Neden": bu üç handle GERÇEKTEN sızmıştı (presence.ts, VITE_MOCK'tan
// bağımsız bundle'a giriyordu). #188 kapsamında presence.ts anonimleştirildi
// (dev-a/b/c); bu liste regresyona karşı KALICI bekçi — silinmez.
const KNOWN_FIXTURE_HANDLES = ["asmarufoglu", "EnesErdemT", "fatih-claude", "esma6", "FatihErenCetin"];

// Literal env-değişkeni adları: gerçek değer değil, adın kendisi bile frontend
// bundle'ında görünmemeli (bir adaptörün yanlışlıkla backend config'ini import
// ettiğinin işareti olur). PEM başlığı gerçek bir özel-anahtar sızıntısı ise
// (GITHUB_APP_PRIVATE_KEY içeriği) daha da kritik.
const SECRET_PATTERNS = [
  { label: "GEMINI_ env adı", pattern: /GEMINI_[A-Z_]+/ },
  { label: "GITHUB_ env adı", pattern: /GITHUB_[A-Z_]+/ },
  { label: "DATABASE_URL", pattern: /DATABASE_URL/ },
  { label: "PEM özel anahtar başlığı", pattern: /-----BEGIN [A-Z ]*PRIVATE KEY-----/ },
];

function walk(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) out.push(...walk(full));
    else out.push(full);
  }
  return out;
}

function extOf(path) {
  const i = path.lastIndexOf(".");
  return i === -1 ? "" : path.slice(i);
}

let dirEntries;
try {
  dirEntries = walk(DIST_DIR);
} catch (err) {
  console.error(`prod-build-guard: '${DIST_DIR}' okunamadı — önce build çalıştırıldı mı? (${err.message})`);
  process.exit(1);
}

const files = dirEntries.filter((p) => SCANNABLE_EXTENSIONS.has(extOf(p)));
if (files.length === 0) {
  console.error(`prod-build-guard: '${DIST_DIR}' altında taranacak dosya yok — build çıktısı boş mu?`);
  process.exit(1);
}

const findings = [];

for (const file of files) {
  const content = readFileSync(file, "utf8");
  const rel = relative(process.cwd(), file);

  for (const { label, pattern } of MOCK_FLAG_MARKERS) {
    if (content.includes(pattern)) {
      findings.push(`[mock-bayrağı] ${label} → "${pattern}" bulundu: ${rel}`);
    }
  }

  for (const handle of KNOWN_FIXTURE_HANDLES) {
    if (content.includes(handle)) {
      findings.push(`[fixture-handle] bilinen kişi/handle sızıntısı → "${handle}" bulundu: ${rel}`);
    }
  }

  for (const { label, pattern } of SECRET_PATTERNS) {
    const m = content.match(pattern);
    if (m) {
      findings.push(`[sır-imzası] ${label} → "${m[0]}" bulundu: ${rel}`);
    }
  }
}

if (findings.length > 0) {
  console.error(`prod-build-guard: ${findings.length} hijyen ihlali bulundu (#188):\n`);
  for (const f of findings) console.error(`  - ${f}`);
  console.error(
    "\nProd build TEMİZ olmalı: mock kapalı + fixture/gerçek-isim/sır sızıntısı yok. " +
      "Bkz. src/frontend/src/lib/api.ts (mock gate) + src/frontend/src/mocks/*.ts (fixture kaynağı).",
  );
  process.exit(1);
}

console.log(`prod-build-guard: temiz — ${files.length} dosya tarandı, ihlal yok (#188).`);
