/** #319 — AskPage tasarım paritesi: "Tarandı" şeridi (gerçek sayım, "karar"
 * GATE'Lİ) · "Takip" önerileri (citation/nearest'ten türetilir) · "son
 * sorular" localStorage geçmişi · turuncu çerçeveli kutu + Enter ipucu.
 *
 * `useAsk`/`useQueryScan` -> `usePolling` -> `api.GET` zincirini en dışından
 * sahteliyoruz: sayfanın kendi türetme mantığını ölçmek istiyoruz, HTTP
 * katmanını değil (activity.test.tsx ile aynı desen).
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const askDurum = vi.hoisted(() => ({
  data: undefined as unknown,
  error: null as unknown,
  isLoading: false,
  isFetching: false,
  dataUpdatedAt: 0,
}));

const scanDurum = vi.hoisted(() => ({
  data: undefined as unknown,
  error: null as unknown,
  isLoading: false,
  isFetching: false,
  dataUpdatedAt: 0,
}));

vi.mock("../src/lib/useAsk", () => ({
  ASK_MAX_LENGTH: 500,
  useAsk: () => askDurum,
}));

vi.mock("../src/lib/useQueryScan", () => ({
  useQueryScan: () => scanDurum,
}));

import AskPage from "../src/pages/AskPage";

const GECMIS_ANAHTAR = "grup54:ask:gecmis";

const TEMEL_CEVAP = {
  answer: "Auth modülüne semih dokundu [cite:T-58].",
  citations: [{ type: "task", ref: "T-58", quote: "Ask endpoint'ini yaz", n: 1 }],
  as_of: "2026-07-29T09:00:00Z",
  last_commit: "abc1234",
  window: null,
  confidence: "high",
  status: "answered",
  searched: [{ type: "task", count: 1 }],
  nearest: [],
};

const NOT_FOUND_CEVAP = {
  answer: "Bu soru için kanonik proje bağlamında yeterli kanıt bulunamadı.",
  citations: [],
  as_of: "2026-07-29T09:00:00Z",
  last_commit: "abc1234",
  window: null,
  confidence: "low",
  status: "not_found",
  searched: [{ type: "task", count: 0 }],
  nearest: [{ type: "decision", ref: "D-57" }],
};

const TEMEL_SCAN = {
  as_of: "2026-07-29T09:00:00Z",
  last_commit: "abc1234",
  searched: [
    { type: "scope", count: 6 },
    { type: "task", count: 14 },
    { type: "decision", count: 0 },
    { type: "event", count: 120 },
    { type: "pr", count: 8 },
  ],
  recent_events: 5,
  recent_event_window_hours: 48,
  recent_events_capped: false,
};

function ayarlaAsk(yeni: Partial<typeof askDurum>) {
  Object.assign(askDurum, {
    data: undefined,
    error: null,
    isLoading: false,
    isFetching: false,
    dataUpdatedAt: 0,
    ...yeni,
  });
}

function ayarlaScan(yeni: Partial<typeof scanDurum>) {
  Object.assign(scanDurum, {
    data: undefined,
    error: null,
    isLoading: false,
    isFetching: false,
    dataUpdatedAt: 0,
    ...yeni,
  });
}

/** Kutuya yazıp "Soruyu gönder"e tıklar — sayfanın TEK soru-sorma yolu. */
async function soruSor(kullanici: ReturnType<typeof userEvent.setup>, metin: string) {
  const kutu = screen.getByLabelText("Projeye sorulacak soru");
  await kullanici.clear(kutu);
  await kullanici.type(kutu, metin);
  await kullanici.click(screen.getByRole("button", { name: "Soruyu gönder" }));
}

beforeEach(() => {
  ayarlaAsk({});
  ayarlaScan({});
  window.localStorage.clear();
});

describe("AskPage — soru kutusu (#319 tasarım paritesi)", () => {
  it("kutu turuncu (marka) çerçeveli — 'gri kutu' değil", () => {
    render(<AskPage />);
    const kutu = screen.getByLabelText("Projeye sorulacak soru");
    // MUTASYON KİLİDİ: border-primary kaldırılıp border-border'a dönülürse kırılır.
    expect(kutu.className).toMatch(/border-primary/);
  });

  it("gönder kontrolü Enter ipucu gösterir, erişilebilir adı 'Soruyu gönder' olarak KALIR", () => {
    render(<AskPage />);
    const gonder = screen.getByRole("button", { name: "Soruyu gönder" });
    expect(gonder.textContent).toMatch(/Enter/);
    expect(gonder).toBeDisabled(); // taslak boşken hâlâ iş-yapmayan-buton kuralı geçerli
  });

  it("örnek sorular BUTON görünümlü (border+bg) — düz link değil", () => {
    render(<AskPage />);
    const ornek = screen.getByRole("button", { name: "Auth modülüne kim dokundu?" });
    // MUTASYON KİLİDİ: className'den `border` kaldırılırsa (düz linke geri
    // dönülürse) bu kırılır.
    expect(ornek.className).toMatch(/border/);
  });

  it("örnek soruya tıklayınca o soru sorulur", async () => {
    ayarlaAsk({ data: TEMEL_CEVAP });
    const kullanici = userEvent.setup();
    render(<AskPage />);

    await kullanici.click(screen.getByRole("button", { name: "Auth modülüne kim dokundu?" }));

    expect(
      within(screen.getByTestId("soru-satiri")).getByText("Auth modülüne kim dokundu?"),
    ).toBeInTheDocument();
  });
});

describe("AskPage — Tarandı şeridi (#319, sıfır-LLM ön-izleme)", () => {
  it("scan verisi gelince GERÇEK görev/olay sayısını gösterir", () => {
    ayarlaScan({ data: TEMEL_SCAN });
    render(<AskPage />);

    const serit = screen.getByTestId("tarama-seridi");
    expect(serit.textContent).toContain("14");
    expect(serit.textContent).toContain("48");
    expect(serit.textContent).toContain("5");
  });

  it("'karar' sayısını HİÇ göstermez — corpus decision indekslemiyor (uydurma yasak)", () => {
    // MUTASYON KİLİDİ: biri şeride "{say('decision')} karar ✓" eklerse bu
    // kırılır — backend her zaman 0 döner (.harness/decisions/ okunmuyor),
    // "0 karar" basmak "karar yok" yalanına dönüşür.
    ayarlaScan({ data: TEMEL_SCAN });
    render(<AskPage />);

    expect(within(screen.getByTestId("tarama-seridi")).queryByText(/karar/i)).toBeNull();
  });

  it("olay sayısı kesinken düz basılır — gereksiz '+' yok", () => {
    ayarlaScan({ data: TEMEL_SCAN });
    render(<AskPage />);

    expect(screen.getByTestId("tarama-olay-sayisi").textContent).toBe("5");
  });

  it("olay çekimi kaynakta sınıra dayandıysa sayı ALT SINIR olarak basılır ('5+')", () => {
    // MUTASYON KİLİDİ (#322 review, Semih): `recent_events_capped` render'da
    // yok sayılırsa bu kırılır. Corpus `event_limit`'e dayandığında pencerede
    // daha fazla olay olabilir; düz "5" basmak EKSİK sayıyı kesinmiş gibi
    // gösterir — tam olarak review'da bildirilen hata.
    ayarlaScan({ data: { ...TEMEL_SCAN, recent_events_capped: true } });
    render(<AskPage />);

    const sayi = screen.getByTestId("tarama-olay-sayisi");
    expect(sayi.textContent).toBe("5+");
    expect(sayi.getAttribute("title")).toMatch(/alt sınır/i);
  });

  it("boş durum, ARANMAYAN 'karar günlüğü'nü aranıyormuş gibi vaat etmez", () => {
    // MUTASYON KİLİDİ (#322 review, Semih): açıklamaya "karar günlüğü" geri
    // eklenirse kırılır. Corpus `.harness/decisions/` okumuyor — şerit decision
    // sayısını zaten gate'liyor; metnin aksini söylemesi aynı sayfa içinde
    // kendi kendine çelişkiydi.
    ayarlaScan({ data: TEMEL_SCAN });
    render(<AskPage />);

    const aciklama = screen.getByText(/üzerinde aranır/);
    expect(aciklama.textContent).not.toMatch(/karar günlüğü/i);
    expect(aciklama.textContent).toMatch(/olay\/PR geçmişi/);
  });

  it("scan verisi yokken (yükleniyor/hata) şerit hiç basılmaz", () => {
    ayarlaScan({ data: undefined });
    render(<AskPage />);

    expect(screen.queryByTestId("tarama-seridi")).toBeNull();
  });

  it("soru sorulmadan ÖNCE de görünür (tasarım: kutunun altında, cevaptan bağımsız)", () => {
    ayarlaScan({ data: TEMEL_SCAN });
    render(<AskPage />);

    expect(screen.getByTestId("tarama-seridi")).toBeInTheDocument();
    // Henüz soru sorulmadı — davetkâr boş durum hâlâ ayakta
    expect(screen.getByText(/Doğal dille sor/)).toBeInTheDocument();
  });
});

describe("AskPage — Takip önerileri (#319, cevabın altında)", () => {
  it("answered cevapta citation'lardan ŞABLONLU takip sorusu üretir", async () => {
    ayarlaAsk({ data: TEMEL_CEVAP });
    const kullanici = userEvent.setup();
    render(<AskPage />);
    await soruSor(kullanici, "Auth modülüne kim dokundu?");

    expect(screen.getByText("Takip:")).toBeInTheDocument();
    // MUTASYON KİLİDİ: TAKIP_SABLONU.task şablonu ya da citation.ref kullanımı
    // bozulursa bu tam metin bulunamaz.
    expect(
      screen.getByRole("button", { name: "T-58 görevinin şu anki durumu nedir?" }),
    ).toBeInTheDocument();
  });

  it("not_found cevapta (citations BOŞ) takip 'nearest'ten türer", async () => {
    ayarlaAsk({ data: NOT_FOUND_CEVAP });
    const kullanici = userEvent.setup();
    render(<AskPage />);
    await soruSor(kullanici, "Rastgele bir şey?");

    expect(
      screen.getByRole("button", { name: "D-57 kararının gerekçesi neydi?" }),
    ).toBeInTheDocument();
  });

  it("takip sorusuna tıklayınca o soru YENİDEN sorulur", async () => {
    ayarlaAsk({ data: TEMEL_CEVAP });
    const kullanici = userEvent.setup();
    render(<AskPage />);
    await soruSor(kullanici, "Auth modülüne kim dokundu?");

    await kullanici.click(
      screen.getByRole("button", { name: "T-58 görevinin şu anki durumu nedir?" }),
    );

    expect(
      within(screen.getByTestId("soru-satiri")).getByText("T-58 görevinin şu anki durumu nedir?"),
    ).toBeInTheDocument();
  });
});

describe("AskPage — son sorular (bu tarayıcıda, localStorage) (#319)", () => {
  it("yeni soru sorulunca localStorage'a en-yeni-önce, TEKRARSIZ eklenir", async () => {
    ayarlaAsk({ data: TEMEL_CEVAP });
    const kullanici = userEvent.setup();
    render(<AskPage />);

    await soruSor(kullanici, "Birinci soru");
    await soruSor(kullanici, "İkinci soru");
    // MUTASYON KİLİDİ: `gecmiseEkle`'deki dedup (`filter((s) => s !== soru)`)
    // kaldırılırsa "Birinci soru" burada İKİNCİ kez eklenir.
    await soruSor(kullanici, "Birinci soru");

    const kayit = JSON.parse(window.localStorage.getItem(GECMIS_ANAHTAR) ?? "[]");
    expect(kayit).toEqual(["Birinci soru", "İkinci soru"]);
  });

  it("geçmiş şeridi MEVCUT soruyu göstermez, öncekileri gösterir", async () => {
    window.localStorage.setItem(GECMIS_ANAHTAR, JSON.stringify(["Eski soru", "Şu anki soru"]));
    ayarlaAsk({ data: TEMEL_CEVAP });
    const kullanici = userEvent.setup();
    render(<AskPage />);
    await soruSor(kullanici, "Şu anki soru");

    const baslik = screen.getByText("Son sorular (bu tarayıcıda)");
    const grup = baslik.closest("div");
    expect(within(grup!).getByText("Eski soru")).toBeInTheDocument();
    // MUTASYON KİLİDİ: `gecmis.filter((g) => g !== soru)` kaldırılırsa mevcut
    // soru burada İKİNCİ kez (takip/soru satırından ayrı olarak) görünürdü.
    expect(within(grup!).queryByText("Şu anki soru")).toBeNull();
  });

  it("geçmişteki bir soruya tıklayınca o soru YENİDEN sorulur", async () => {
    window.localStorage.setItem(GECMIS_ANAHTAR, JSON.stringify(["Eski soru"]));
    ayarlaAsk({ data: TEMEL_CEVAP });
    const kullanici = userEvent.setup();
    render(<AskPage />);
    await soruSor(kullanici, "Şu anki soru");

    await kullanici.click(screen.getByRole("button", { name: "Eski soru" }));

    expect(within(screen.getByTestId("soru-satiri")).getByText("Eski soru")).toBeInTheDocument();
  });

  it("localStorage BOZUKSA (private mode/kota) sayfa beyaz ekran OLMAZ", () => {
    // MUTASYON KİLİDİ: `gecmisOku` içindeki try/catch kaldırılırsa JSON.parse
    // bozuk veride fırlatır ve mount anında sayfa patlar.
    window.localStorage.setItem(GECMIS_ANAHTAR, "{bozuk-json");

    expect(() => render(<AskPage />)).not.toThrow();
  });
});

/* ── #355 — dar zemin uyarısı + karar kaydı atfı ─────────────────────────────
   Bu iki blok #319'unkilerle AYNI dosyada birleşti (ikisi de `ask.test.tsx`'i
   sıfırdan yaratmıştı). #319'un kurgusu taban alındı: `ayarlaAsk` + `soruSor`
   tek yol olsun, iki ayrı sahteleme dili yan yana yaşamasın. */

const KARARLI_CEVAP = {
  ...TEMEL_CEVAP,
  answer: "Hosted demo VDS üzerinde çalışıyor [cite:D-46].",
  citations: [
    {
      type: "decision",
      ref: "D-46",
      quote: "Fly.io terk edildi — backend VDS'e taşındı",
      n: 1,
    },
  ],
  searched: [
    { type: "scope", count: 14 },
    { type: "task", count: 22 },
    { type: "decision", count: 11 },
    { type: "event", count: 129 },
    { type: "pr", count: 71 },
  ],
};

describe("AskPage — dar zemin uyarısı (#355)", () => {
  it("degraded DOLU ise uyarı şeridi basılır", async () => {
    /* `QueryResult.degraded` API'de #330'dan beri vardı ama bu sayfa onu HİÇ
       basmıyordu. Canlıda (30 Tem) embed kotası bitince API dürüstçe düşüşü
       bildiriyor, kullanıcı ise kelime eşleşmesiyle seçilmiş bir cevabı tam
       yetenekle üretilmiş sanıyordu.
       MUTASYON KİLİDİ: `{data.degraded && <DarZeminSeridi …/>}` satırını sil. */
    const kullanici = userEvent.setup();
    ayarlaAsk({
      data: { ...KARARLI_CEVAP, degraded: "semantik retrieval kullanılamadı (429)" },
      dataUpdatedAt: Date.now(),
    });
    render(<AskPage />);
    await soruSor(kullanici, "hosted demo kararı neydi?");

    const serit = screen
      .getAllByRole("status")
      .find((e) => /semantik arama kullanılamadı/i.test(e.textContent ?? ""));
    expect(serit).toBeDefined();
    expect(serit!.textContent).toMatch(/eksik olabilir/);
  });

  it("degraded BOŞ ise dar-zemin uyarısı YOK (yanlış alarm basmıyoruz)", async () => {
    const kullanici = userEvent.setup();
    ayarlaAsk({ data: KARARLI_CEVAP, dataUpdatedAt: Date.now() });
    render(<AskPage />);
    await soruSor(kullanici, "hosted demo kararı neydi?");
    const uyari = screen
      .queryAllByRole("status")
      .find((e) => /semantik arama kullanılamadı/i.test(e.textContent ?? ""));
    expect(uyari).toBeUndefined();
  });

  it("uzun sağlayıcı hatası ekranı kusmaz ama TAMAMI title'da kalır", async () => {
    // Gemini'nin 429 gövdesi ~1 KB JSON. Kırpılır ama teşhis kaybolmaz.
    const kullanici = userEvent.setup();
    const uzun = `semantik retrieval kullanılamadı (${"x".repeat(600)})`;
    ayarlaAsk({ data: { ...KARARLI_CEVAP, degraded: uzun }, dataUpdatedAt: Date.now() });
    render(<AskPage />);
    await soruSor(kullanici, "soru");

    const tam = screen.getByTitle(uzun);
    expect(tam.textContent!.length).toBeLessThan(200);
  });
});

describe("AskPage — karar kaydı atfı (#355)", () => {
  it("karar tipli atıf kaynak listesinde 'karar' olarak görünür", async () => {
    /* Korpusta karar YOKKEN bu ekran bu hâli hiç göstermiyordu: makbuz
       `decision: 0` basıyor, ürün eski görev metninden "Fly backend"
       cevaplıyordu. */
    const kullanici = userEvent.setup();
    ayarlaAsk({ data: KARARLI_CEVAP, dataUpdatedAt: Date.now() });
    render(<AskPage />);
    await soruSor(kullanici, "hosted demo kararı neydi?");
    expect(screen.getByText("karar")).toBeInTheDocument();
    expect(screen.getByText(/Fly\.io terk edildi/)).toBeInTheDocument();
  });

  it("cevap makbuzu karar sayısını da basar", async () => {
    const kullanici = userEvent.setup();
    ayarlaAsk({ data: KARARLI_CEVAP, dataUpdatedAt: Date.now() });
    render(<AskPage />);
    await soruSor(kullanici, "hosted demo kararı neydi?");
    // Sayı ayrı <span>'de (tabular-nums) → paragrafın tamamı okunur.
    const makbuz = screen.getByText(/Aranan kaynaklar/).closest("p");
    expect(makbuz?.textContent).toMatch(/11\s*karar/);
  });
});
