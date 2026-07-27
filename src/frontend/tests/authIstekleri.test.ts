/** T-294 (#297/#298) — `kayitOlIstegi`/`girisYapIstegi`: HTTP durum kodu →
 * `AuthEylemSonucu.tur` eşlemesinin KENDİSİ. `register.test.tsx`/`login.test.tsx`
 * bu fonksiyonları MOCK'lar (sayfa render mantığını izole eder) — bu dosya ise
 * tam tersini yapar: `api.POST`'u mock'layıp GERÇEK eşleme mantığını (useAuth.ts
 * switch-case'leri) kilitler.
 *
 * MUTASYON KİLİTLERİ: `case 409`/`case 401` dallarını kaldır (default'a düşsün)
 * → ilgili testler kırılır (tur "beklenmeyen" olur, "email_kayitli"/"gecersiz_giris" DEĞİL).
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../src/lib/api";
import { girisYapIstegi, kayitOlIstegi } from "../src/lib/useAuth";

vi.mock("../src/lib/api", () => ({
  api: { POST: vi.fn() },
}));

const mockPost = api.POST as unknown as ReturnType<typeof vi.fn>;

function basarili(body: { handle?: string | null; avatar_url?: string | null; email?: string | null }) {
  return { data: body, error: undefined, response: { status: 200, headers: new Headers() } };
}

function basarisiz(status: number, body: unknown, headers: Record<string, string> = {}) {
  return { data: undefined, error: body, response: { status, headers: new Headers(headers) } };
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("kayitOlIstegi — POST /auth/register eşlemesi", () => {
  it("201 → basarili + kullanıcı alanları taşınır", async () => {
    mockPost.mockResolvedValue(
      basarili({ handle: null, avatar_url: null, email: "a@b.com" }),
    );
    const s = await kayitOlIstegi("a@b.com", "sifre1234");
    expect(s).toEqual({
      tur: "basarili",
      kullanici: { handle: null, avatar_url: null, email: "a@b.com" },
    });
    expect(mockPost).toHaveBeenCalledWith("/auth/register", {
      body: { email: "a@b.com", password: "sifre1234" },
    });
  });

  it("409 → email_kayitli + backend'in kendi mesajı", async () => {
    mockPost.mockResolvedValue(
      basarisiz(409, { error: "http_409", message: "Bu e-posta ile zaten bir hesap var.", status: 409 }),
    );
    const s = await kayitOlIstegi("a@b.com", "sifre1234");
    expect(s.tur).toBe("email_kayitli");
    expect(s).toMatchObject({ mesaj: "Bu e-posta ile zaten bir hesap var." });
  });

  it("422 → politika_ihlali + backend'in politika mesajı", async () => {
    mockPost.mockResolvedValue(
      basarisiz(422, { error: "http_422", message: "Parola en az 8 karakter olmalı.", status: 422 }),
    );
    const s = await kayitOlIstegi("a@b.com", "kisa");
    expect(s.tur).toBe("politika_ihlali");
    expect(s).toMatchObject({ mesaj: "Parola en az 8 karakter olmalı." });
  });

  it("429 → cok_fazla_deneme + Retry-After başlığından saniye okunur", async () => {
    mockPost.mockResolvedValue(
      basarisiz(
        429,
        { error: "http_429", message: "Çok fazla deneme yapıldı — birazdan tekrar deneyin.", status: 429 },
        { "Retry-After": "12" },
      ),
    );
    const s = await kayitOlIstegi("a@b.com", "sifre1234");
    expect(s.tur).toBe("cok_fazla_deneme");
    expect(s).toMatchObject({ saniye: 12 });
  });

  it("503 → kapali", async () => {
    mockPost.mockResolvedValue(
      basarisiz(503, { error: "http_503", message: "E-posta ile üyelik yapılandırılmamış.", status: 503 }),
    );
    const s = await kayitOlIstegi("a@b.com", "sifre1234");
    expect(s.tur).toBe("kapali");
  });

  it("beklenmeyen durum kodu (500) → beklenmeyen, HATA YUTULMAZ", async () => {
    mockPost.mockResolvedValue(
      basarisiz(500, { error: "internal", message: "Beklenmedik hata", status: 500 }),
    );
    const s = await kayitOlIstegi("a@b.com", "sifre1234");
    expect(s.tur).toBe("beklenmeyen");
  });

  it("ağ hatası (api.POST reddeder) → beklenmeyen, sayfa çökmez", async () => {
    mockPost.mockRejectedValue(new Error("Failed to fetch"));
    const s = await kayitOlIstegi("a@b.com", "sifre1234");
    expect(s).toEqual({ tur: "beklenmeyen", mesaj: "Failed to fetch" });
  });
});

describe("girisYapIstegi — POST /auth/login eşlemesi", () => {
  it("200 → basarili", async () => {
    mockPost.mockResolvedValue(
      basarili({ handle: "FatihErenCetin", avatar_url: null, email: null }),
    );
    const s = await girisYapIstegi("a@b.com", "sifre1234");
    expect(s).toEqual({
      tur: "basarili",
      kullanici: { handle: "FatihErenCetin", avatar_url: null, email: null },
    });
  });

  it("401 → gecersiz_giris + backend'in GENEL mesajı (ayrım YOK)", async () => {
    mockPost.mockResolvedValue(
      basarisiz(401, { error: "http_401", message: "E-posta ya da parola hatalı.", status: 401 }),
    );
    const s = await girisYapIstegi("yok@b.com", "her-sey");
    expect(s.tur).toBe("gecersiz_giris");
    expect(s).toMatchObject({ mesaj: "E-posta ya da parola hatalı." });
  });

  it("429 → cok_fazla_deneme + saniye", async () => {
    mockPost.mockResolvedValue(
      basarisiz(
        429,
        { error: "http_429", message: "Çok fazla deneme yapıldı — birazdan tekrar deneyin.", status: 429 },
        { "Retry-After": "5" },
      ),
    );
    const s = await girisYapIstegi("a@b.com", "x");
    expect(s.tur).toBe("cok_fazla_deneme");
    expect(s).toMatchObject({ saniye: 5 });
  });
});
