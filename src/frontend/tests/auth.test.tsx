/** #79 (daraltılmış) — `useAuth`: anonim NORMAL, gerçek hata GÖRÜNÜR.
 *
 * Bu dosya bugün üç ayrı katmanda bulunan aynı arıza sınıfını kilitler:
 * bir sinyalin, "yokluk" ile ayırt edilemez bir değere çökmesi.
 *   backend : 429 -> severity="low" sahte Detection  (#252)
 *   frontend: boş gövde -> error="" (falsy) -> hata yutuluyor
 *   auth    : 401 -> "hata" sanılırsa anonim ziyaretçiye kırmızı kutu çıkar
 *
 * 401 bir arıza değil, sözleşmenin normal hâlidir: demo giriş İSTEMEZ.
 */
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useAuth } from "../src/lib/useAuth";

/** fetch'i yol bazlı sahteler; her yol {status, body} döndürür. */
function fetchSahtele(yanitlar: Record<string, { status: number; body?: unknown }>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (girdi: RequestInfo | URL) => {
      const yol = String(typeof girdi === "string" ? girdi : (girdi as Request).url ?? girdi);
      const anahtar = Object.keys(yanitlar).find((k) => yol.includes(k));
      const y = anahtar ? yanitlar[anahtar] : { status: 404 };
      return {
        status: y.status,
        ok: y.status >= 200 && y.status < 300,
        json: async () => {
          if (y.body === undefined) throw new SyntaxError("bos govde");
          return y.body;
        },
      } as unknown as Response;
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useAuth", () => {
  it("401 ANONIM demektir — hata DEĞİL", async () => {
    // MUTASYON KİLİDİ: useAuth'ta 401 dalını kaldır (throw'a düşsün) -> error
    // dolar, LoginPage/AppLayout anonim ziyaretçiye kırmızı hata kutusu gösterir.
    fetchSahtele({
      "/auth/config": { status: 200, body: { enabled: true } },
      "/auth/me": { status: 401 },
    });

    const { result } = renderHook(() => useAuth());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.enabled).toBe(true);
    expect(result.current.kullanici).toBeNull();
    expect(result.current.error).toBeNull(); // ← anonim sessizdir
  });

  it("yapılandırılmamışsa enabled=false, hata YOK", async () => {
    // Sırlar yokken uygulama açılır ve bunu DÜRÜSTÇE söyler (Groq deseni).
    fetchSahtele({ "/auth/config": { status: 200, body: { enabled: false } } });

    const { result } = renderHook(() => useAuth());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.enabled).toBe(false);
    expect(result.current.kullanici).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it("enabled=false iken /auth/me'ye HİÇ gidilmez", async () => {
    fetchSahtele({ "/auth/config": { status: 200, body: { enabled: false } } });

    const { result } = renderHook(() => useAuth());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const cagrilar = (globalThis.fetch as unknown as { mock: { calls: unknown[][] } }).mock.calls;
    const meCagrisi = cagrilar.some((c) => String(c[0]).includes("/auth/me"));
    expect(meCagrisi).toBe(false); // boşuna istek atma
  });

  it("giriş yapılmışsa kullanıcı döner", async () => {
    fetchSahtele({
      "/auth/config": { status: 200, body: { enabled: true } },
      "/auth/me": { status: 200, body: { handle: "FatihErenCetin", avatar_url: null } },
    });

    const { result } = renderHook(() => useAuth());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.kullanici?.handle).toBe("FatihErenCetin");
    expect(result.current.error).toBeNull();
  });

  it("GERÇEK hata yutulmaz — 500 error alanına düşer", async () => {
    // Simetrik kilit: 401 sessiz olmalı AMA 500 sessiz OLMAMALI. İkisini
    // birbirine karıştıran bir düzeltme bu testte yakalanır.
    fetchSahtele({
      "/auth/config": { status: 200, body: { enabled: true } },
      "/auth/me": { status: 500, body: { detail: "patladi" } },
    });

    const { result } = renderHook(() => useAuth());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.error).not.toBeNull();
    expect(result.current.kullanici).toBeNull();
  });

  it("bozuk /auth/me gövdesi (handle yok) hata sayılır", async () => {
    fetchSahtele({
      "/auth/config": { status: 200, body: { enabled: true } },
      "/auth/me": { status: 200, body: { avatar_url: "x" } },
    });

    const { result } = renderHook(() => useAuth());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.error).not.toBeNull();
  });
});
