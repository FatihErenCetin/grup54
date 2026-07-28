/** T-309 — `saglayiciAyarlariniGetir`/`saglayiciGuncelle`/`saglayiciTestEt`/
 * `mcpConfigGetir`: HTTP durum kodu → `tur` eşlemesinin KENDİSİ (useSettings.ts).
 * `repoSeciciIstekleri.test.ts`'in kalıbının AYNISI: `api.GET`/`api.PUT`/
 * `api.POST` mock'lanır, GERÇEK eşleme mantığı (switch-case'ler) kilitlenir —
 * sayfa testleri (ayarlar.test.tsx) bu fonksiyonların KENDİLERİNİ mock'lar,
 * bu dosya ise tam tersini yapar.
 *
 * MUTASYON KİLİTLERİ (görev brifi §Testler):
 *  - `saglayiciAyarlariniGetir`'de `response.status === 404` dalını kaldır
 *    (default'a düşsün) → "hosted'da 404 → yok" testi kırılır (tur "yok"
 *    yerine "beklenmeyen" döner) — BU, AppLayout/AyarlarPage'in "hosted'da
 *    sayfayı gizle" kapısının TEK dayanağı, kırılırsa gizleme kapısı da kırılır.
 *  - `saglayiciGuncelle`'de `case 422`'yi kaldır (default'a düşsün) →
 *    "gecersiz" testi kırılır.
 *  - `saglayiciTestEt`'te 200'ü `calisiyor:false` iken "beklenmeyen"e
 *    çevirirsen (sahte-başarısızlık-yutma) → "calisiyor:false AYNEN taşınır"
 *    testi kırılır.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../src/lib/api";
import {
  mcpConfigGetir,
  saglayiciAyarlariniGetir,
  saglayiciGuncelle,
  saglayiciTestEt,
} from "../src/lib/useSettings";

vi.mock("../src/lib/api", () => ({
  api: { GET: vi.fn(), PUT: vi.fn(), POST: vi.fn() },
}));

const mockGet = api.GET as unknown as ReturnType<typeof vi.fn>;
const mockPut = api.PUT as unknown as ReturnType<typeof vi.fn>;
const mockPost = api.POST as unknown as ReturnType<typeof vi.fn>;

function basarili(body: unknown) {
  return { data: body, error: undefined, response: { status: 200, headers: new Headers() } };
}

function basarisiz(status: number, body: unknown) {
  return { data: undefined, error: body, response: { status, headers: new Headers() } };
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("saglayiciAyarlariniGetir — GET /settings/saglayici eşlemesi", () => {
  it("200 → basarili + mode/saglayici/anahtarlar/ollama_url taşınır", async () => {
    mockGet.mockResolvedValue(
      basarili({
        mode: "local",
        saglayici: "gemini",
        anahtarlar: { gemini: "ANAH…4f2c", groq: null },
        ollama_url: "http://localhost:11434",
      }),
    );
    const s = await saglayiciAyarlariniGetir();
    expect(s).toEqual({
      tur: "basarili",
      mode: "local",
      saglayici: "gemini",
      anahtarlar: { gemini: "ANAH…4f2c", groq: null },
      ollama_url: "http://localhost:11434",
    });
    expect(mockGet).toHaveBeenCalledWith("/settings/saglayici");
  });

  it("404 → yok (hosted — MUTASYON KİLİDİ: bu dal AppLayout/AyarlarPage'in gizleme kapısının tek dayanağı)", async () => {
    mockGet.mockResolvedValue(
      basarisiz(404, { error: "http_404", message: "Bu uç yalnız local modda vardır.", status: 404 }),
    );
    const s = await saglayiciAyarlariniGetir();
    expect(s).toEqual({ tur: "yok" });
  });

  it("beklenmeyen durum kodu (500) → beklenmeyen, HATA YUTULMAZ", async () => {
    mockGet.mockResolvedValue(basarisiz(500, { error: "internal", message: "patladı", status: 500 }));
    const s = await saglayiciAyarlariniGetir();
    expect(s.tur).toBe("beklenmeyen");
  });

  it("ağ hatası → beklenmeyen, sayfa çökmez", async () => {
    mockGet.mockRejectedValue(new Error("Failed to fetch"));
    const s = await saglayiciAyarlariniGetir();
    expect(s).toEqual({ tur: "beklenmeyen", mesaj: "Failed to fetch" });
  });
});

describe("saglayiciGuncelle — PUT /settings/saglayici eşlemesi", () => {
  it("200 → basarili + DOĞRU gövdeyle çağrılır", async () => {
    mockPut.mockResolvedValue(
      basarili({
        mode: "local",
        saglayici: "gemini",
        anahtarlar: { gemini: "YENI…anah", groq: null },
        ollama_url: "http://localhost:11434",
      }),
    );
    const s = await saglayiciGuncelle({ saglayici: "gemini", anahtar: "gercek-anahtar" });
    expect(s.tur).toBe("basarili");
    expect(mockPut).toHaveBeenCalledWith("/settings/saglayici", {
      body: { saglayici: "gemini", anahtar: "gercek-anahtar" },
    });
  });

  it("anahtar undefined bırakılırsa gövdede de undefined kalır (mevcut anahtar korunur)", async () => {
    mockPut.mockResolvedValue(
      basarili({
        mode: "local",
        saglayici: "gemini",
        anahtarlar: { gemini: "ANAH…4f2c", groq: null },
        ollama_url: "http://localhost:11434",
      }),
    );
    await saglayiciGuncelle({ saglayici: "gemini", anahtar: undefined });
    expect(mockPut).toHaveBeenCalledWith("/settings/saglayici", {
      body: { saglayici: "gemini", anahtar: undefined },
    });
  });

  it("404 → yok", async () => {
    mockPut.mockResolvedValue(
      basarisiz(404, { error: "http_404", message: "Bu uç yalnız local modda vardır.", status: 404 }),
    );
    const s = await saglayiciGuncelle({ saglayici: "ollama", ollama_url: "kotu-url" });
    expect(s).toEqual({ tur: "yok" });
  });

  it("422 → gecersiz + backend'in mesajı (MUTASYON KİLİDİ: case 422'yi kaldır)", async () => {
    mockPut.mockResolvedValue(
      basarisiz(422, {
        error: "http_422",
        message: "Ollama URL'i geçersiz — yalnız localhost/127.0.0.1 kabul edilir.",
        status: 422,
      }),
    );
    const s = await saglayiciGuncelle({ saglayici: "ollama", ollama_url: "https://evil.example" });
    expect(s.tur).toBe("gecersiz");
    expect(s).toMatchObject({
      mesaj: "Ollama URL'i geçersiz — yalnız localhost/127.0.0.1 kabul edilir.",
    });
  });

  it("beklenmeyen durum kodu (500) → beklenmeyen, HATA YUTULMAZ", async () => {
    mockPut.mockResolvedValue(basarisiz(500, { error: "internal", message: "patladı", status: 500 }));
    const s = await saglayiciGuncelle({ saglayici: "gemini", anahtar: "x" });
    expect(s.tur).toBe("beklenmeyen");
  });

  it("ağ hatası → beklenmeyen, sayfa çökmez", async () => {
    mockPut.mockRejectedValue(new Error("Failed to fetch"));
    const s = await saglayiciGuncelle({ saglayici: "gemini" });
    expect(s).toEqual({ tur: "beklenmeyen", mesaj: "Failed to fetch" });
  });
});

describe("saglayiciTestEt — POST /settings/test eşlemesi", () => {
  it("200 calisiyor:true → sonuc + backend'in mesajı AYNEN", async () => {
    mockPost.mockResolvedValue(basarili({ calisiyor: true, mesaj: "Bağlantı başarılı." }));
    const s = await saglayiciTestEt("gemini");
    expect(s).toEqual({ tur: "sonuc", calisiyor: true, mesaj: "Bağlantı başarılı." });
    expect(mockPost).toHaveBeenCalledWith("/settings/test", { body: { saglayici: "gemini" } });
  });

  it("200 calisiyor:false → sonuc AYNEN taşınır, 'beklenmeyen'e ÇEVRİLMEZ (sahte-başarı yasak, MUTASYON KİLİDİ)", async () => {
    mockPost.mockResolvedValue(
      basarili({ calisiyor: false, mesaj: "Gemini anahtarı geçersiz veya yetkisiz (401)." }),
    );
    const s = await saglayiciTestEt("gemini");
    expect(s).toEqual({
      tur: "sonuc",
      calisiyor: false,
      mesaj: "Gemini anahtarı geçersiz veya yetkisiz (401).",
    });
  });

  it("404 → yok", async () => {
    mockPost.mockResolvedValue(
      basarisiz(404, { error: "http_404", message: "Bu uç yalnız local modda vardır.", status: 404 }),
    );
    const s = await saglayiciTestEt("groq");
    expect(s).toEqual({ tur: "yok" });
  });

  it("beklenmeyen durum kodu (500) → beklenmeyen, HATA YUTULMAZ", async () => {
    mockPost.mockResolvedValue(basarisiz(500, { error: "internal", message: "patladı", status: 500 }));
    const s = await saglayiciTestEt("ollama");
    expect(s.tur).toBe("beklenmeyen");
  });

  it("ağ hatası → beklenmeyen, sayfa çökmez", async () => {
    mockPost.mockRejectedValue(new Error("Failed to fetch"));
    const s = await saglayiciTestEt("gemini");
    expect(s).toEqual({ tur: "beklenmeyen", mesaj: "Failed to fetch" });
  });
});

describe("mcpConfigGetir — GET /settings/mcp eşlemesi", () => {
  it("200 → basarili + config_json/yol taşınır", async () => {
    mockGet.mockResolvedValue(
      basarili({ config_json: '{"mcpServers":{}}', yol: "/Users/x/repo/.mcp.json" }),
    );
    const s = await mcpConfigGetir();
    expect(s).toEqual({
      tur: "basarili",
      config_json: '{"mcpServers":{}}',
      yol: "/Users/x/repo/.mcp.json",
    });
    expect(mockGet).toHaveBeenCalledWith("/settings/mcp");
  });

  it("404 → yok (hosted)", async () => {
    mockGet.mockResolvedValue(
      basarisiz(404, { error: "http_404", message: "Bu uç yalnız local modda vardır.", status: 404 }),
    );
    const s = await mcpConfigGetir();
    expect(s).toEqual({ tur: "yok" });
  });

  it("beklenmeyen durum kodu → beklenmeyen", async () => {
    mockGet.mockResolvedValue(basarisiz(502, { error: "gemini_error", message: "patladı", status: 502 }));
    const s = await mcpConfigGetir();
    expect(s.tur).toBe("beklenmeyen");
  });

  it("ağ hatası → beklenmeyen, sayfa çökmez", async () => {
    mockGet.mockRejectedValue(new Error("Failed to fetch"));
    const s = await mcpConfigGetir();
    expect(s).toEqual({ tur: "beklenmeyen", mesaj: "Failed to fetch" });
  });
});
