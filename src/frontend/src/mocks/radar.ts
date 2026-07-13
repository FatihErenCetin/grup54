/**
 * Mock veri (#21) — VITE_MOCK=1 iken tipli client bu fixture'lardan beslenir.
 *
 * İki güvence:
 * - Tip zorunluluğu: fixture `RadarResponse` şemasını DOLDURMAK ZORUNDA —
 *   kontrat değişirse burası derlemede kırılır (mock kontrattan drift edemez).
 * - Dürüstlük: vakalar uydurma değil, repo tarihimizin GERÇEK çakışmalarından
 *   (#135↔#137 config.py, #137↔#132 .env.example, #88↔#89 ci.yml — backtest
 *   dataset'iyle aynı hikâye). Yine de mock'tur: UI "ÖRNEK VERİ" rozeti basar.
 */

import type { components } from "../api/schema.d.ts";

type RadarResponse = components["schemas"]["RadarResponse"];
type Detection = components["schemas"]["Detection"];

export const mockDetections: Detection[] = [
  {
    id: "det-config-py",
    kind: "conflict",
    actors: ["esma6"], // iki branch de ayni aktorun (gercek vaka boyleydi)
    branches: ["T-50-gemini-adapter", "T-16-github-ingest"],
    files: [
      "src/backend/ensemble/config.py",
      "src/backend/pyproject.toml",
      "tests/unit/test_config.py",
    ],
    severity: "high",
    confidence: 0.93,
    rationale:
      "İki branch de Settings'e aynı bölgede alan ekliyor (Gemini retry ayarları ↔ GitHub App alanları) — birleştirmede metinsel çakışma kaçınılmaz.",
  },
  {
    id: "det-env-example",
    kind: "conflict",
    actors: ["esma6", "FatihErenCetin"],
    branches: ["T-16-github-ingest", "T-46-app-kaydi"],
    files: [".env.example"],
    severity: "high",
    confidence: 0.88,
    rationale:
      "Aynı env şablonunun bitişik satırlarına iki taraf da yeni anahtar ekliyor (GITHUB_REPO_* ↔ webhook satırları); dosya küçük, çarpışma alanı dar.",
  },
  {
    id: "det-radar-engine",
    kind: "conflict",
    actors: ["asmarufoglu", "fatih-claude"],
    branches: ["T-23-semantik-hunk-cosine", "T-27-backtest-dataset"],
    files: ["src/backend/ensemble/engine/radar.py"],
    severity: "med",
    confidence: 0.71,
    rationale:
      "Farklı dosyalarda ama aynı modülün (engine/radar) aday-üretim mantığına dokunuluyor; imzalar şimdilik uyumlu, semantik yakınlık yüksek.",
  },
  {
    id: "det-ci-yml",
    kind: "conflict",
    actors: ["asmarufoglu", "FatihErenCetin"],
    branches: ["T-77-scaffold-sertlestirme", "T-20-openapi-client"],
    files: [".github/workflows/ci.yml"],
    severity: "low",
    confidence: 0.42,
    rationale:
      "İkisi de CI dosyasına adım ekliyor ama farklı job'larda; dosya-kesişimi var, satır çakışması beklenmiyor.",
  },
];

export function mockRadarResponse(): RadarResponse {
  // updated_at her çağrıda taze — polling'in "Son güncelleme" akışı mock'ta da
  // gerçek davranışıyla görünür (rozet zaten "örnek veri" diyor)
  return { detections: mockDetections, updated_at: new Date().toISOString() };
}

/** openapi-fetch custom fetch — yol bazlı fixture yönlendirme */
export function mockFetch(req: Request): Response {
  const path = new URL(req.url).pathname;
  if (path === "/radar") {
    return Response.json(mockRadarResponse());
  }
  return Response.json({ detail: `mock: bilinmeyen yol ${path}` }, { status: 404 });
}

// Presence örnek verisi ayrı modülde (mocks/presence.ts): o modül bundle'a
// bilerek girer (şerit S3'e dek hep örnek), bu dosya ise yalnız VITE_MOCK'ta
// dynamic import'la yüklenir — prod bundle'a radar fixture'ı sızmaz.
