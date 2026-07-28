/** #33 · #272 — Activity sayfası: dört durum dalı + gruplama + UTC parse kilidi.
 *
 * Review bulgusu (Semih): 166 satırlık yeni UI'da tek test yoktu ve
 * `new Date(iso)` naive-UTC damgayı tarayıcı YEREL saati sanıyordu —
 * Europe/Istanbul'da 3 saat kayma ve yanlış GÜN başlığı.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import ActivityPage from "../src/pages/ActivityPage";

/* `useEvents` -> `usePolling` -> `api.GET` zincirini en dışından sahteliyoruz:
   sayfanın kendi durum dallarını ölçmek istiyoruz, HTTP katmanını değil. */
const durum = vi.hoisted(() => ({
  data: undefined as unknown,
  error: null as unknown,
  isLoading: false,
  isFetching: false,
  dataUpdatedAt: 0,
}));

vi.mock("../src/lib/useEvents", () => ({
  useEvents: () => durum,
}));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  // MemoryRouter şart: aktör çipi artık linkli (#129) → <Link> router context ister.
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

function ayarla(yeni: Partial<typeof durum>) {
  Object.assign(durum, {
    data: undefined,
    error: null,
    isLoading: false,
    isFetching: false,
    dataUpdatedAt: 0,
    ...yeni,
  });
}

function ev(
  id: string,
  actor: string,
  ts: string,
  type = "commit",
  actorVerified?: boolean,
) {
  return {
    id,
    type,
    actor,
    branch: `T-${id}`,
    files: ["src/x.py"],
    ts,
    ref: id,
    ...(actorVerified === undefined ? {} : { actor_verified: actorVerified }),
  };
}

/** #319 testleri "Bugün"/"Dün" başlığına bağlı — `gunBasligi` GERÇEK sistem
 * saatine (`new Date()`) göre karşılaştırır, bu yüzden sabit bir takvim
 * tarihi ("2026-07-27" gibi) zamanla "bugün" olmaktan çıkar. Yerel öğlene
 * yakın bir saat (gece yarısı/DST sınırından uzak) kullanılır. */
function isoBugun(saat = 9): string {
  const d = new Date();
  d.setHours(saat, 0, 0, 0);
  return d.toISOString();
}
function isoDun(saat = 9): string {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  d.setHours(saat, 0, 0, 0);
  return d.toISOString();
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ActivityPage — dört durum dalı", () => {
  it("yükleniyor: iskelet gösterir", () => {
    ayarla({ isLoading: true });
    render(<ActivityPage />, { wrapper });
    expect(screen.getByLabelText(/Olay akışı yükleniyor/i)).toBeTruthy();
  });

  it('error="" (falsy) bile HATA sayılır — sessizce yutulmaz', async () => {
    // MUTASYON KİLİDİ: `error != null` -> `if (error)` yapılırsa bu test kırılır.
    // openapi-fetch boş gövdeli non-ok yanıtta error olarak "" verebiliyor;
    // falsy olduğu için `if (error)` onu görmez ve sayfa "boş feed" gibi görünür.
    ayarla({ error: "", data: undefined });
    render(<ActivityPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeTruthy();
    });
  });

  it("boş sonuç HATA DEĞİL — dürüst boş durum gösterir", () => {
    ayarla({ data: { events: [], latest_ts: null } });
    render(<ActivityPage />, { wrapper });
    expect(screen.getByText(/Henüz olay yok/i)).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("başlık Title Case (#316/A5): 'Olay Akışı', 'Olay akışı' DEĞİL", () => {
    // MUTASYON KİLİDİ: h1'i eski "Olay akışı"ya geri çevir -> bu test kırılır.
    ayarla({ data: { events: [], latest_ts: null } });
    render(<ActivityPage />, { wrapper });
    expect(screen.getByRole("heading", { name: "Olay Akışı" })).toBeTruthy();
  });

  it("veri varken geçici poll hatası listeyi GİZLEMEZ", () => {
    ayarla({ data: { events: [ev("e1", "esma", "2026-07-27T09:00:00")] }, error: "geçici" });
    render(<ActivityPage />, { wrapper });
    expect(screen.getByLabelText("esma olayları")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("ActivityPage — gruplama", () => {
  it("gün ve aktör bazında gruplar", () => {
    ayarla({
      data: {
        events: [
          ev("e1", "esma", "2026-07-27T09:00:00"),
          ev("e2", "esma", "2026-07-27T10:00:00"),
          ev("e3", "enes", "2026-07-27T11:00:00"),
        ],
      },
    });
    render(<ActivityPage />, { wrapper });
    // İki ayrı aktör kutusu; esma'nınkinde iki olay.
    expect(screen.getByLabelText("esma olayları").children.length).toBe(2);
    expect(screen.getByLabelText("enes olayları").children.length).toBe(1);
  });

  it("bozuk tarih ekrana 'Invalid Date' basmaz", () => {
    ayarla({ data: { events: [ev("e1", "esma", "bozuk-tarih")] } });
    render(<ActivityPage />, { wrapper });
    expect(screen.queryByText(/Invalid Date/i)).toBeNull();
    expect(screen.getByText(/Tarihi okunamayan olaylar/i)).toBeTruthy();
  });
});

describe("ActivityPage — naive-UTC parse (review blocker'ı)", () => {
  it("zone eki olmayan damgayı UTC sayar, yerel saat SANMAZ", () => {
    // Backend `"2026-07-27T22:30:00"` üretiyor (Z YOK).
    //   new Date(iso)      -> Europe/Istanbul'da 27 Tem 22:30  (YANLIŞ)
    //   new Date(iso+"Z")  -> Europe/Istanbul'da 28 Tem 01:30  (DOĞRU)
    // MUTASYON KİLİDİ: parseUtc'yi `new Date(iso)`'ya geri çevir -> kırılır.
    const naive = "2026-07-27T22:30:00";
    expect(new Date(`${naive}Z`).toISOString()).toBe("2026-07-27T22:30:00.000Z");

    ayarla({ data: { events: [ev("e1", "esma", naive)] } });
    render(<ActivityPage />, { wrapper });

    const beklenen = new Date(`${naive}Z`).toLocaleTimeString("tr-TR", {
      hour: "2-digit",
      minute: "2-digit",
    });
    expect(screen.getByText(beklenen)).toBeTruthy();

    // Naive parse edilseydi gösterilecek olan saat EKRANDA OLMAMALI.
    const yanlis = new Date(naive).toLocaleTimeString("tr-TR", {
      hour: "2-digit",
      minute: "2-digit",
    });
    if (yanlis !== beklenen) {
      expect(screen.queryByText(yanlis)).toBeNull();
    }
  });

  it("zone eki OLAN damgayı bozmaz (çift Z eklemez)", () => {
    ayarla({ data: { events: [ev("e1", "esma", "2026-07-27T22:30:00Z")] } });
    render(<ActivityPage />, { wrapper });
    expect(screen.queryByText(/Invalid Date/i)).toBeNull();
    expect(screen.getByLabelText("esma olayları")).toBeTruthy();
  });

  it("sıralama epoch üzerinden — naive/aware karışımı bozmaz", () => {
    // String karşılaştırması bu ikisini yanlış sıralardı ('Z' > rakam).
    ayarla({
      data: {
        events: [
          ev("eski", "esma", "2026-07-27T09:00:00Z"),
          ev("yeni", "esma", "2026-07-27T10:00:00"),
        ],
      },
    });
    render(<ActivityPage />, { wrapper });
    const liste = screen.getByLabelText("esma olayları");
    // En yeni önce: 10:00 satırı ilk sırada olmalı.
    expect(liste.children[0].textContent).toContain("T-yeni");
  });
});

describe("ActivityPage — aktör doğrulama göstergesi (#296)", () => {
  it("tüm olaylar doğrulanmış: aktör çipinde rozet YOK", () => {
    ayarla({
      data: {
        events: [
          ev("e1", "esma6", "2026-07-27T09:00:00", "commit", true),
          ev("e2", "esma6", "2026-07-27T10:00:00", "commit", true),
        ],
      },
    });
    render(<ActivityPage />, { wrapper });
    expect(screen.queryByTestId("actor-unverified-badge")).toBeNull();
  });

  it("bir grup içindeki TEK bir olay bile eşleşmemişse çip bunu gösterir", () => {
    // MUTASYON KİLİDİ: `grupDogrulanmisMi`'in `.some(...)` mantığı
    // `.every(...)`'e çevrilirse (yalnız HEPSİ eşleşmediğinde işaretle) bu
    // test kırılır — tek kötü örnek bile gizlenmemeli.
    ayarla({
      data: {
        events: [
          ev("e1", "Merge Simulation", "2026-07-27T09:00:00", "commit", false),
          ev("e2", "Merge Simulation", "2026-07-27T10:00:00", "commit", true),
        ],
      },
    });
    render(<ActivityPage />, { wrapper });
    expect(screen.getByTestId("actor-unverified-badge")).toBeInTheDocument();
  });

  it("actor_verified alanı hiç yoksa (eski/mock veri): DOĞRULANMIŞ sayılır", () => {
    // additive+varsayılanlı model (ensemble.models.NormalizedEvent) — alanı
    // taşımayan veri sessizce "eşleşmedi" görünmemeli.
    ayarla({ data: { events: [ev("e1", "esma", "2026-07-27T09:00:00")] } });
    render(<ActivityPage />, { wrapper });
    expect(screen.queryByTestId("actor-unverified-badge")).toBeNull();
  });

  it("iki ayrı aktör grubu: yalnız eşleşmeyen olan rozet taşır", () => {
    ayarla({
      data: {
        events: [
          ev("e1", "esma6", "2026-07-27T09:00:00", "commit", true),
          ev("e2", "Merge Simulation", "2026-07-27T09:30:00", "commit", false),
        ],
      },
    });
    render(<ActivityPage />, { wrapper });
    const esmaGrubu = screen.getByLabelText("esma6 olayları").closest("div.overflow-hidden");
    const simGrubu = screen.getByLabelText("Merge Simulation olayları").closest("div.overflow-hidden");
    expect(esmaGrubu?.querySelector('[data-testid="actor-unverified-badge"]')).toBeNull();
    expect(simGrubu?.querySelector('[data-testid="actor-unverified-badge"]')).not.toBeNull();
  });
});

describe("ActivityPage — aktör türü filtresi: İnsan | Hepsi | Yalnız ajan (#319)", () => {
  it("varsayılan 'Hepsi': hem insan hem ajan olayları görünür", () => {
    ayarla({
      data: {
        events: [ev("e1", "esma", isoBugun(9)), ev("e2", "fatih-claude", isoBugun(10))],
      },
    });
    render(<ActivityPage />, { wrapper });
    expect(screen.getByLabelText("esma olayları")).toBeInTheDocument();
    expect(screen.getByLabelText("fatih-claude olayları")).toBeInTheDocument();
  });

  it("'Yalnız ajan' filtresi insan olaylarını GİZLER", async () => {
    ayarla({
      data: {
        events: [ev("e1", "esma", isoBugun(9)), ev("e2", "fatih-claude", isoBugun(10))],
      },
    });
    const kullanici = userEvent.setup();
    render(<ActivityPage />, { wrapper });

    await kullanici.click(screen.getByRole("button", { name: "Yalnız ajan" }));

    // MUTASYON KİLİDİ: `aktorTipiSezgisi` filtrede kullanılmazsa (ör. hep
    // "hepsi" davranışına düşerse) esma burada hâlâ görünür kalırdı.
    expect(screen.queryByLabelText("esma olayları")).toBeNull();
    expect(screen.getByLabelText("fatih-claude olayları")).toBeInTheDocument();
  });

  it("'İnsan' filtresi ajan olaylarını GİZLER", async () => {
    ayarla({
      data: {
        events: [ev("e1", "esma", isoBugun(9)), ev("e2", "fatih-claude", isoBugun(10))],
      },
    });
    const kullanici = userEvent.setup();
    render(<ActivityPage />, { wrapper });

    await kullanici.click(screen.getByRole("button", { name: "İnsan" }));

    expect(screen.getByLabelText("esma olayları")).toBeInTheDocument();
    expect(screen.queryByLabelText("fatih-claude olayları")).toBeNull();
  });

  it("filtrede sonuç yokken dürüst boş satır gösterir (toplam sayıyı da söyler)", async () => {
    ayarla({ data: { events: [ev("e1", "fatih-claude", isoBugun(9))] } });
    const kullanici = userEvent.setup();
    render(<ActivityPage />, { wrapper });

    await kullanici.click(screen.getByRole("button", { name: "İnsan" }));

    expect(screen.getByText(/Bu filtrede olay yok/)).toBeInTheDocument();
    expect(screen.queryByLabelText("fatih-claude olayları")).toBeNull();
  });
});

describe("ActivityPage — görünüm anahtarı: Düz | Aktöre göre (#319)", () => {
  it("varsayılan 'Aktöre göre': aktör grup başlıkları görünür", () => {
    ayarla({ data: { events: [ev("e1", "esma", isoBugun(9))] } });
    render(<ActivityPage />, { wrapper });
    expect(screen.getByLabelText("esma olayları")).toBeInTheDocument();
  });

  it("'Düz' seçilince aktör alt-gruplaması KALKAR — gün ayraçlı düz akış", async () => {
    ayarla({
      data: {
        events: [ev("e1", "esma", isoBugun(9)), ev("e2", "enes", isoBugun(10))],
      },
    });
    const kullanici = userEvent.setup();
    render(<ActivityPage />, { wrapper });

    await kullanici.click(screen.getByRole("button", { name: "Düz" }));

    // MUTASYON KİLİDİ: `gorunum === "duz"` dalı kaldırılırsa (her zaman
    // gruplu render edilirse) bu aria-label hiç bulunamaz.
    const duzListe = screen.getByLabelText("Bugün olayları (düz)");
    expect(duzListe).toBeInTheDocument();
    expect(duzListe.children.length).toBe(2); // iki olay da AYNI düz listede, alt-grup YOK
    expect(screen.queryByLabelText("esma olayları")).toBeNull();
  });

  it("Düz görünümde her satırda aktör çipi görünür (grup başlığı olmadan)", async () => {
    ayarla({ data: { events: [ev("e1", "esma", isoBugun(9))] } });
    const kullanici = userEvent.setup();
    render(<ActivityPage />, { wrapper });

    await kullanici.click(screen.getByRole("button", { name: "Düz" }));

    expect(within(screen.getByLabelText("Bugün olayları (düz)")).getByText("esma")).toBeInTheDocument();
  });
});

describe("ActivityPage — '↑ N yeni' rozeti (#319, istemci tarafı)", () => {
  it("ilk yüklemede rozet YOK (taban ilk veriyle dondurulur)", () => {
    ayarla({ data: { events: [ev("e1", "esma", isoBugun(9))] } });
    render(<ActivityPage />, { wrapper });
    expect(screen.queryByRole("button", { name: /yeni/ })).toBeNull();
  });

  it("sonraki pollde gelen YENİ olayları sayar", async () => {
    ayarla({ data: { events: [ev("e1", "esma", isoBugun(9))] } });
    const { rerender } = render(<ActivityPage />, { wrapper });

    ayarla({
      data: {
        events: [
          ev("e1", "esma", isoBugun(9)),
          ev("e2", "enes", isoBugun(10)),
          ev("e3", "enes", isoBugun(11)),
        ],
      },
    });
    rerender(<ActivityPage />);

    // MUTASYON KİLİDİ: taban hiç dondurulmazsa (ya da her render'da events'e
    // eşitlenirse) bu rozet hiç görünmez / hep 0 kalır.
    expect(screen.getByRole("button", { name: /2 yeni/ })).toBeInTheDocument();
  });

  it("rozete tıklamak tabanı günceller — rozet KAYBOLUR", async () => {
    ayarla({ data: { events: [ev("e1", "esma", isoBugun(9))] } });
    const kullanici = userEvent.setup();
    const { rerender } = render(<ActivityPage />, { wrapper });

    ayarla({
      data: { events: [ev("e1", "esma", isoBugun(9)), ev("e2", "enes", isoBugun(10))] },
    });
    rerender(<ActivityPage />);

    await kullanici.click(screen.getByRole("button", { name: /1 yeni/ }));

    expect(screen.queryByRole("button", { name: /yeni/ })).toBeNull();
  });

  it("'yeni' sayısı aktör filtresinden BAĞIMSIZDIR (filtre değişince kaymaz)", async () => {
    ayarla({ data: { events: [ev("e1", "esma", isoBugun(9))] } });
    const kullanici = userEvent.setup();
    const { rerender } = render(<ActivityPage />, { wrapper });

    ayarla({
      data: {
        events: [ev("e1", "esma", isoBugun(9)), ev("e2", "fatih-claude", isoBugun(10))],
      },
    });
    rerender(<ActivityPage />);
    expect(screen.getByRole("button", { name: /1 yeni/ })).toBeInTheDocument();

    // MUTASYON KİLİDİ: `yeniSayisi` `filtrelenmis`ten hesaplanırsa (tam
    // `events` yerine) filtre değişince bu sayı YANLIŞLIKLA kayardı.
    await kullanici.click(screen.getByRole("button", { name: "Yalnız ajan" }));
    expect(screen.getByRole("button", { name: /1 yeni/ })).toBeInTheDocument();
  });
});

describe("ActivityPage — Kendiliğinden Daily kartı (#319)", () => {
  it("Bugün/Dün satırlarını GERÇEK aktör+tür sayımından üretir", () => {
    ayarla({
      data: {
        events: [
          ev("e1", "esma", isoBugun(9), "commit"),
          ev("e2", "esma", isoBugun(10), "commit"),
          ev("e3", "semih", isoBugun(11), "pr"),
          ev("e4", "enes", isoDun(9), "issue"),
        ],
      },
    });
    render(<ActivityPage />, { wrapper });

    const kart = screen.getByTestId("daily-karti");
    // MUTASYON KİLİDİ: `aktorRollupSatirlari`'nin sayaç mantığı bozulursa
    // (ör. toplam yerine son elemanı sayarsa) bu tam metinler bulunamaz.
    expect(within(kart).getByText("esma: 2 commit")).toBeInTheDocument();
    expect(within(kart).getByText("semih: 1 PR")).toBeInTheDocument();
    expect(within(kart).getByText("enes: 1 issue")).toBeInTheDocument();
  });

  it("olay yokken bölümü DÜRÜSTÇE boş gösterir (uydurma satır yok)", () => {
    ayarla({ data: { events: [ev("e1", "esma", isoBugun(9))] } });
    render(<ActivityPage />, { wrapper });

    const kart = screen.getByTestId("daily-karti");
    expect(within(kart).getByText("olay yok")).toBeInTheDocument(); // Dün boş
  });

  it("blocker satırı HİÇ basılmaz — NormalizedEvent/PresenceEntry taşımıyor (gate'li)", () => {
    ayarla({ data: { events: [ev("e1", "esma", isoBugun(9))] } });
    render(<ActivityPage />, { wrapper });
    expect(screen.queryByText(/blocker/i)).toBeNull();
  });

  it("'Panoya kopyala' GERÇEK rollup metnini panoya yazar", async () => {
    // DİKKAT (ayarlar.test.tsx ile aynı bulgu): userEvent.setup() jsdom'un
    // KENDİ Clipboard stub'ını kurar — Object.defineProperty bundan SONRA.
    const kullanici = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
    ayarla({ data: { events: [ev("e1", "esma", isoBugun(9), "commit")] } });
    render(<ActivityPage />, { wrapper });

    await kullanici.click(screen.getByRole("button", { name: "Panoya kopyala" }));

    expect(writeText).toHaveBeenCalledWith(expect.stringContaining("esma: 1 commit"));
    expect(await screen.findByText("Kopyalandı ✓")).toBeInTheDocument();
  });
});
