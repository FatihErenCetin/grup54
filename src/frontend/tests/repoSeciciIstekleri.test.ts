/** #79'un kalan dilimi (T-79) — `kurulumUrlIstegi`/`kurulumlariGetir`/`repolariGetir`/
 * `repolariGuncelle`: HTTP durum kodu → `tur` eşlemesinin KENDİSİ (useRepoSecici.ts).
 * `authIstekleri.test.ts`'in kalıbının AYNISI: `api.GET`/`api.PUT` mock'lanır, GERÇEK
 * eşleme mantığı (switch-case'ler) kilitlenir — sayfa testleri (repoSecici.test.tsx)
 * bu fonksiyonların KENDİLERİNİ mock'lar, bu dosya ise tam tersini yapar.
 *
 * MUTASYON KİLİTLERİ: `case 401`/`case 403`/`case 503` dallarını kaldır (default'a
 * düşsün) → ilgili testler kırılır ("giris_gerekli"/"izinsiz"/"kapali" yerine
 * "beklenmeyen" döner).
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../src/lib/api";
import {
  kurulumUrlIstegi,
  kurulumlariGetir,
  repolariGetir,
  repolariGuncelle,
} from "../src/lib/useRepoSecici";

vi.mock("../src/lib/api", () => ({
  api: { GET: vi.fn(), PUT: vi.fn() },
}));

const mockGet = api.GET as unknown as ReturnType<typeof vi.fn>;
const mockPut = api.PUT as unknown as ReturnType<typeof vi.fn>;

function basarili(body: unknown) {
  return { data: body, error: undefined, response: { status: 200, headers: new Headers() } };
}

function basarisiz(status: number, body: unknown) {
  return { data: undefined, error: body, response: { status, headers: new Headers() } };
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("kurulumUrlIstegi — GET /auth/install-url eşlemesi", () => {
  it("200 → basarili + url taşınır", async () => {
    mockGet.mockResolvedValue(basarili({ url: "https://github.com/apps/x/installations/new" }));
    const s = await kurulumUrlIstegi();
    expect(s).toEqual({ tur: "basarili", url: "https://github.com/apps/x/installations/new" });
    expect(mockGet).toHaveBeenCalledWith("/auth/install-url");
  });

  it("401 → giris_gerekli", async () => {
    mockGet.mockResolvedValue(
      basarisiz(401, { error: "http_401", message: "Oturum bulunamadı", status: 401 }),
    );
    const s = await kurulumUrlIstegi();
    expect(s).toEqual({ tur: "giris_gerekli" });
  });

  it("503 → kapali + backend'in mesajı", async () => {
    mockGet.mockResolvedValue(
      basarisiz(503, {
        error: "http_503",
        message: "GitHub App kurulum akışı yapılandırılmamış — GITHUB_APP_ID eksik",
        status: 503,
      }),
    );
    const s = await kurulumUrlIstegi();
    expect(s.tur).toBe("kapali");
    expect(s).toMatchObject({
      mesaj: "GitHub App kurulum akışı yapılandırılmamış — GITHUB_APP_ID eksik",
    });
  });

  it("beklenmeyen durum kodu (500) → beklenmeyen, HATA YUTULMAZ", async () => {
    mockGet.mockResolvedValue(
      basarisiz(500, { error: "internal", message: "Beklenmedik hata", status: 500 }),
    );
    const s = await kurulumUrlIstegi();
    expect(s.tur).toBe("beklenmeyen");
  });

  it("ağ hatası → beklenmeyen, sayfa çökmez", async () => {
    mockGet.mockRejectedValue(new Error("Failed to fetch"));
    const s = await kurulumUrlIstegi();
    expect(s).toEqual({ tur: "beklenmeyen", mesaj: "Failed to fetch" });
  });
});

describe("kurulumlariGetir — GET /auth/installations eşlemesi", () => {
  it("200 → basarili + installations taşınır (yoksa boş liste)", async () => {
    mockGet.mockResolvedValue(basarili({}));
    const s = await kurulumlariGetir();
    expect(s).toEqual({ tur: "basarili", installations: [] });
  });

  it("401 → giris_gerekli", async () => {
    mockGet.mockResolvedValue(
      basarisiz(401, { error: "http_401", message: "Oturum bulunamadı", status: 401 }),
    );
    const s = await kurulumlariGetir();
    expect(s).toEqual({ tur: "giris_gerekli" });
  });

  it("503 → kapali + backend'in mesajı (App hiç yapılandırılmamış)", async () => {
    mockGet.mockResolvedValue(
      basarisiz(503, {
        error: "http_503",
        message: "GitHub App kurulum akışı yapılandırılmamış — GITHUB_APP_ID eksik",
        status: 503,
      }),
    );
    const s = await kurulumlariGetir();
    expect(s.tur).toBe("kapali");
  });

  it("beklenmeyen durum kodu → beklenmeyen", async () => {
    mockGet.mockResolvedValue(basarisiz(502, { error: "github_error", message: "patladı", status: 502 }));
    const s = await kurulumlariGetir();
    expect(s.tur).toBe("beklenmeyen");
  });
});

describe("repolariGetir — GET /auth/repos eşlemesi", () => {
  it("200 → basarili + selected/active/demo taşınır", async () => {
    mockGet.mockResolvedValue(
      basarili({ selected: ["a/b"], active: "a/b", demo: "grup54/ensemble" }),
    );
    const s = await repolariGetir();
    expect(s).toEqual({
      tur: "basarili",
      selected: ["a/b"],
      active: "a/b",
      demo: "grup54/ensemble",
    });
  });

  it("401 → giris_gerekli", async () => {
    mockGet.mockResolvedValue(
      basarisiz(401, { error: "http_401", message: "Oturum bulunamadı", status: 401 }),
    );
    const s = await repolariGetir();
    expect(s).toEqual({ tur: "giris_gerekli" });
  });

  it("beklenmeyen durum kodu → beklenmeyen, HATA YUTULMAZ", async () => {
    mockGet.mockResolvedValue(basarisiz(500, { error: "internal", message: "patladı", status: 500 }));
    const s = await repolariGetir();
    expect(s.tur).toBe("beklenmeyen");
  });
});

describe("repolariGuncelle — PUT /auth/repos eşlemesi", () => {
  it("200 → basarili + selected/active taşınır, DOĞRU gövdeyle çağrılır", async () => {
    mockPut.mockResolvedValue(basarili({ selected: ["a/b"], active: "a/b" }));
    const s = await repolariGuncelle(["a/b"], "a/b");
    expect(s).toEqual({ tur: "basarili", selected: ["a/b"], active: "a/b" });
    expect(mockPut).toHaveBeenCalledWith("/auth/repos", { body: { repos: ["a/b"], active: "a/b" } });
  });

  it("401 → giris_gerekli", async () => {
    mockPut.mockResolvedValue(
      basarisiz(401, { error: "http_401", message: "Oturum bulunamadı", status: 401 }),
    );
    const s = await repolariGuncelle(["a/b"], "a/b");
    expect(s).toEqual({ tur: "giris_gerekli" });
  });

  it("403 → izinsiz + backend'in mesajı (MUTASYON KİLİDİ: case 403'ü kaldır)", async () => {
    mockPut.mockResolvedValue(
      basarisiz(403, {
        error: "http_403",
        message: "Şu repolara erişiminiz yok (kurulumlarınızda değil): ['x/y']",
        status: 403,
      }),
    );
    const s = await repolariGuncelle(["x/y"], "x/y");
    expect(s.tur).toBe("izinsiz");
    expect(s).toMatchObject({
      mesaj: "Şu repolara erişiminiz yok (kurulumlarınızda değil): ['x/y']",
    });
  });

  it("beklenmeyen durum kodu (500) → beklenmeyen, HATA YUTULMAZ", async () => {
    mockPut.mockResolvedValue(
      basarisiz(500, { error: "internal", message: "Beklenmedik hata", status: 500 }),
    );
    const s = await repolariGuncelle(["a/b"], "a/b");
    expect(s.tur).toBe("beklenmeyen");
  });

  it("ağ hatası → beklenmeyen, sayfa çökmez", async () => {
    mockPut.mockRejectedValue(new Error("Failed to fetch"));
    const s = await repolariGuncelle(["a/b"], "a/b");
    expect(s).toEqual({ tur: "beklenmeyen", mesaj: "Failed to fetch" });
  });
});
