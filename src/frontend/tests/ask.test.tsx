/** AskPage testleri (#355).
 *
 * Bu dosya NEDEN yeni: AskPage'in hiç testi yoktu (`pageTitles.test.tsx`
 * yalnız başlığa bakıyordu). `QueryResult.degraded` API'de #330'dan beri
 * vardı ama bu sayfa onu HİÇ basmıyordu — ve hiçbir test bunu sormuyordu.
 * "Asla sessizce düşme" sözleşmesi model katmanında üç yerde uygulanmış
 * (radar · scope · query), arayüzde YALNIZ radar'da bağlanmıştı.
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { components } from "../src/api/schema.d.ts";
import AskPage from "../src/pages/AskPage";

type QueryResponse = components["schemas"]["QueryResponse"];

const mockUseAsk = vi.fn();
/* Kısmi mock: modül `useAsk` DIŞINDA sabitler de dışa veriyor (ASK_MAX_LENGTH)
   ve AskPage onları kullanıyor — komple mock'lamak sayfayı çökertir. */
vi.mock("../src/lib/useAsk", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../src/lib/useAsk")>()),
  useAsk: (soru: string) => mockUseAsk(soru),
}));

const TEMEL: QueryResponse = {
  answer: "Hosted demo VDS üzerinde çalışıyor [cite:D-46].",
  citations: [
    {
      type: "decision",
      ref: "D-46",
      quote: "Fly.io terk edildi — backend VDS'e taşındı",
      url: null,
      range: null,
      n: 1,
    },
  ],
  as_of: "2026-07-30T16:00:00Z",
  last_commit: "abc1234",
  window: null,
  confidence: "high",
  status: "answered",
  searched: [
    { type: "scope", count: 14 },
    { type: "task", count: 22 },
    { type: "decision", count: 9 },
    { type: "event", count: 129 },
    { type: "pr", count: 71 },
  ],
  nearest: [],
  degraded: null,
};

function cevap(uzerine: Partial<QueryResponse> = {}) {
  return {
    data: { ...TEMEL, ...uzerine },
    error: null,
    isLoading: false,
    isFetching: false,
    dataUpdatedAt: Date.now(),
  };
}

function wrapper({ children }: { children: ReactNode }) {
  return <MemoryRouter>{children}</MemoryRouter>;
}

async function sor(kullanici: ReturnType<typeof userEvent.setup>) {
  await kullanici.type(screen.getByRole("textbox"), "hosted demo kararı neydi?");
  await kullanici.click(screen.getByRole("button", { name: "Sor" }));
}

beforeEach(() => {
  mockUseAsk.mockReturnValue(cevap());
});

describe("AskPage — dar zemin uyarısı (#355)", () => {
  it("degraded DOLU ise uyarı şeridi basılır", async () => {
    /* Asıl kilit. Canlıda (30 Tem) embed kotası bitince API dürüstçe
       `degraded` döndürüyordu ama kullanıcı bunu HİÇ görmüyor, kelime
       eşleşmesiyle seçilmiş bir cevabı tam yetenekle üretilmiş sanıyordu.
       MUTASYON KİLİDİ: `{data.degraded && <DarZeminSeridi …/>}` satırını sil
       -> bu test kırılır. */
    const kullanici = userEvent.setup();
    mockUseAsk.mockReturnValue(
      cevap({ degraded: "semantik retrieval kullanılamadı (GeminiTransientError: 429 ...)" }),
    );
    render(<AskPage />, { wrapper });
    await sor(kullanici);

    const serit = screen.getByRole("status");
    expect(within(serit).getByText(/semantik arama kullanılamadı/i)).toBeInTheDocument();
    expect(within(serit).getByText(/eksik olabilir/)).toBeInTheDocument();
  });

  it("degraded BOŞ ise uyarı YOK (yanlış alarm basmıyoruz)", async () => {
    const kullanici = userEvent.setup();
    render(<AskPage />, { wrapper });
    await sor(kullanici);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("uzun sağlayıcı hatası ekranı kusmaz ama TAMAMI title'da kalır", async () => {
    // Gemini'nin 429 gövdesi ~1 KB JSON. Kırpılır (arayüz okunur kalsın) ama
    // teşhis kaybolmaz — tam metin `title` özniteliğinde.
    const kullanici = userEvent.setup();
    const uzun = `semantik retrieval kullanılamadı (${"x".repeat(600)})`;
    mockUseAsk.mockReturnValue(cevap({ degraded: uzun }));
    render(<AskPage />, { wrapper });
    await sor(kullanici);

    const tam = screen.getByTitle(uzun);
    expect(tam).toBeInTheDocument();
    expect(tam.textContent!.length).toBeLessThan(200);
  });
});

describe("AskPage — karar kaydı atfı (#355)", () => {
  it("karar tipli atıf kaynak listesinde 'karar' olarak görünür", async () => {
    /* Korpusta karar YOKKEN bu ekran hiç bu hâli göstermiyordu: makbuz
       `decision: 0` basıyor, ürün eski görev metninden "Fly backend"
       cevaplıyordu. */
    const kullanici = userEvent.setup();
    render(<AskPage />, { wrapper });
    await sor(kullanici);
    expect(screen.getByText("karar")).toBeInTheDocument();
    expect(screen.getByText(/Fly\.io terk edildi/)).toBeInTheDocument();
  });

  it("arama makbuzu karar sayısını da basar", async () => {
    const kullanici = userEvent.setup();
    render(<AskPage />, { wrapper });
    await sor(kullanici);
    // Sayı ayrı <span>'de (tabular-nums) → düz metin eşleşmesi çalışmaz;
    // makbuz paragrafının TAMAMI okunur.
    const makbuz = screen.getByText(/Aranan kaynaklar/).closest("p");
    expect(makbuz?.textContent).toMatch(/9\s*karar/);
  });
});
