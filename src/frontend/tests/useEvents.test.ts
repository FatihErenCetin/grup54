/** #273 — artımlı olay çekimi (`since` imleci + id ile tekilleştirme).
 *
 * Ölçüm (canlı, 2026-07-27, 663 olay): since YOK 223 KB · since VAR 26 KB.
 * ETag zaten çalışıyordu (304 + 0 bayt) ama TÜM akıştan hesaplandığı için
 * tek bir yeni olay 223 KB'ın tamamını yeniden getirtiyordu.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const istekler: Array<Record<string, unknown> | undefined> = [];
let sonrakiYanit: { data?: unknown; error?: unknown } = { data: undefined };

vi.mock("../src/lib/api", () => ({
  api: {
    GET: vi.fn(async (_yol: string, secenek?: { params?: { query?: Record<string, unknown> } }) => {
      istekler.push(secenek?.params?.query);
      return sonrakiYanit;
    }),
  },
}));

// `usePolling`'i sahteleyip fetcher'ı DOĞRUDAN çağırabilir hale getiriyoruz:
// burada test edilen şey react-query değil, birikim/imleç mantığı.
let yakalananFetcher: (() => Promise<{ data?: unknown; error?: unknown }>) | null = null;
vi.mock("../src/lib/usePolling", () => ({
  usePolling: (_anahtar: unknown, fetcher: () => Promise<{ data?: unknown; error?: unknown }>) => {
    yakalananFetcher = fetcher;
    return { data: undefined, error: null, isLoading: false, isFetching: false, dataUpdatedAt: 0 };
  },
}));

import { _birikimiSifirla, _birikimSayisi, useEvents } from "../src/lib/useEvents";

function olay(id: string, ts: string) {
  return { id, type: "commit", actor: "esma", branch: null, files: [], ts, ref: id };
}

/** Hook'u kurup fetcher'ı bir kez koştur. */
async function cek(yanit: { data?: unknown; error?: unknown }) {
  sonrakiYanit = yanit;
  useEvents();
  if (!yakalananFetcher) throw new Error("fetcher yakalanamadi");
  return yakalananFetcher();
}

beforeEach(() => {
  _birikimiSifirla();
  istekler.length = 0;
  yakalananFetcher = null;
});

describe("#273 — artımlı çekim", () => {
  it("İLK istekte `since` GÖNDERMEZ (tam akış gerekiyor)", async () => {
    await cek({ data: { events: [olay("a", "2026-07-27T09:00:00")], latest_ts: "2026-07-27T09:00:00" } });
    expect(istekler[0]).toEqual({});
  });

  it("İKİNCİ istekte imleci gönderir — asıl kazanç bu", async () => {
    // MUTASYON KİLİDİ: `since: imlec` kaldırılırsa her poll tüm akışı çeker
    // (canlıda 223 KB vs 26 KB) ve bu test kırılır.
    await cek({ data: { events: [olay("a", "2026-07-27T09:00:00")], latest_ts: "2026-07-27T09:00:00" } });
    await cek({ data: { events: [], latest_ts: "2026-07-27T09:00:00" } });
    expect(istekler[1]).toEqual({ since: "2026-07-27T09:00:00" });
  });

  it("gelen olayları BİRİKTİRİR — artımlı yanıt eskiyi silmez", async () => {
    await cek({ data: { events: [olay("a", "2026-07-27T09:00:00")], latest_ts: "2026-07-27T09:00:00" } });
    const ikinci = await cek({
      data: { events: [olay("b", "2026-07-27T10:00:00")], latest_ts: "2026-07-27T10:00:00" },
    });
    const idler = (ikinci.data as { events: Array<{ id: string }> }).events.map((e) => e.id);
    expect(idler.sort()).toEqual(["a", "b"]);
  });

  it("sınırdaki olay tekrar gelince ÇOĞALMAZ (id ile tekilleştirme)", async () => {
    // Backend `since`'i DAHİL ediyor (`>=`) — sınırdaki olay bilerek tekrar
    // gelir. Doğru tarafa yanılmış: tekrarı eleyebiliriz, kaybı elemezdik.
    await cek({ data: { events: [olay("a", "2026-07-27T09:00:00")], latest_ts: "2026-07-27T09:00:00" } });
    const ikinci = await cek({
      data: {
        events: [olay("a", "2026-07-27T09:00:00"), olay("b", "2026-07-27T10:00:00")],
        latest_ts: "2026-07-27T10:00:00",
      },
    });
    expect((ikinci.data as { events: unknown[] }).events).toHaveLength(2);
    expect(_birikimSayisi()).toBe(2);
  });

  it("HATA gelince birikimi ve imleci BOZMAZ", async () => {
    // MUTASYON KİLİDİ: hata dalında erken dönüş kaldırılıp imleç yine
    // ilerletilirse, başarısız istekteki aralık BİR DAHA hiç istenmez —
    // olaylar kalıcı olarak kaybolur ve hiçbir hata görünmez.
    await cek({ data: { events: [olay("a", "2026-07-27T09:00:00")], latest_ts: "2026-07-27T09:00:00" } });
    await cek({ error: "ağ koptu" });
    expect(_birikimSayisi()).toBe(1);

    await cek({ data: { events: [], latest_ts: "2026-07-27T09:00:00" } });
    expect(istekler[2]).toEqual({ since: "2026-07-27T09:00:00" });
  });

  it("imleç GERİ SARMAZ (sunucu eski damga dönerse)", async () => {
    // Yeniden kurulum / saat kayması sonrası sunucu daha eski bir latest_ts
    // dönebilir. Geri sarsaydık aynı aralığı tekrar tekrar çeker, yeni
    // olayları ise imleç ilerlemediği için kaçırırdık.
    await cek({ data: { events: [olay("b", "2026-07-27T10:00:00")], latest_ts: "2026-07-27T10:00:00" } });
    await cek({ data: { events: [], latest_ts: "2026-07-20T08:00:00" } });
    await cek({ data: { events: [], latest_ts: "2026-07-27T10:00:00" } });
    expect(istekler[2]).toEqual({ since: "2026-07-27T10:00:00" });
  });

  it("latest_ts null gelirse imleç KORUNUR", async () => {
    await cek({ data: { events: [olay("a", "2026-07-27T09:00:00")], latest_ts: "2026-07-27T09:00:00" } });
    await cek({ data: { events: [], latest_ts: null } });
    await cek({ data: { events: [], latest_ts: null } });
    expect(istekler[2]).toEqual({ since: "2026-07-27T09:00:00" });
  });
});
