/** T-309 — AyarlarPage (/ayarlar): sağlayıcı ayarları formu + Claude Code (MCP)
 * bağlama bölümü. `useSaglayiciAyarlari`/`useMcpConfig`/`saglayiciGuncelle`/
 * `saglayiciTestEt` MOCK'lanır (gerçek fetch/api YOK) — sayfa mantığı (hosted
 * gizleme, maske dürüstlüğü, test sonucunun uydurulmaması, MCP dürüstlük
 * uyarısı) izole test edilir. `repoSecici.test.tsx`'in kalıbının AYNISI.
 *
 * MUTASYON KİLİTLERİ (görev brifi §Testler):
 *  - `ayarlar.data.tur === "yok"` dalını kaldır (Navigate silinsin) →
 *    "hosted'da /radar'a yönlendirir" testi kırılır
 *  - Gemini/Ollama/Groq kartlarında `anahtar: anahtar || undefined` yerine
 *    `anahtar: anahtar` yazılırsa (boş string gönderilirse) → "boş bırakılırsa
 *    anahtar gönderilmez" testi kırılır
 *  - Test sonucunda `calisiyor:false`'u "başarılı" gibi gösterirsen (ton'u
 *    'basarili' yaparsan) → "test başarısızsa dürüstçe gösterilir" testi kırılır
 *  - MCP dürüstlük uyarısını kopyalama sonrasına koşullarsan (yalnız
 *    `kopyalandi` iken göster) → "uyarı HER ZAMAN görünür" testi kırılır
 *
 * #332 EK KİLİTLER (araç-bağımsız MCP):
 *  - Araç seçimini yok sayıp hep ilk aracın parçacığını basarsan → "araç
 *    değişince YOL ve BİÇİM de değişir" testi kırılır (Codex TOML okur)
 *  - `mcp?.tur !== "basarili"` koşulunu kaldırıp eski koşulsuz Navigate'e
 *    dönersen → "hosted'da SESSİZ 404 yok" testi kırılır
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import AyarlarPage from "../src/pages/AyarlarPage";

const mockUseSaglayiciAyarlari = vi.fn();
const mockUseMcpConfig = vi.fn();
const mockSaglayiciGuncelle = vi.fn();
const mockSaglayiciTestEt = vi.fn();

vi.mock("../src/lib/useSettings", () => ({
  useSaglayiciAyarlari: () => mockUseSaglayiciAyarlari(),
  useMcpConfig: (enabled: boolean) => mockUseMcpConfig(enabled),
  saglayiciGuncelle: (payload: unknown) => mockSaglayiciGuncelle(payload),
  saglayiciTestEt: (saglayici: string) => mockSaglayiciTestEt(saglayici),
}));

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/ayarlar"]}>
      <Routes>
        <Route path="/ayarlar" element={<AyarlarPage />} />
        <Route path="/radar" element={<div>RADAR SAYFASI</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

const ayarBasarili = {
  tur: "basarili" as const,
  mode: "local" as const,
  saglayici: "gemini" as const,
  anahtarlar: { gemini: "ANAH…4f2c", groq: null },
  ollama_url: "http://localhost:11434",
};

const mcpAraclar = [
  {
    arac: "claude-code",
    ad: "Claude Code",
    bicim: "json" as const,
    yol: "/Users/x/grup54/.mcp.json",
    config_metni: '{\n  "mcpServers": {}\n}',
    paylasimli_dosya: false,
    aciklama: "Yapıştırdıktan sonra Claude Code'u YENİDEN BAŞLAT.",
    kaynak: "https://code.claude.com/docs/en/mcp",
  },
  {
    arac: "codex",
    ad: "Codex CLI",
    bicim: "toml" as const,
    yol: "~/.codex/config.toml",
    config_metni: '[mcp_servers.ensemble]\ncommand = "uv"\n',
    paylasimli_dosya: true,
    aciklama: "Codex JSON DEĞİL TOML okur.",
    kaynak: "https://developers.openai.com/codex/mcp",
  },
];

const mcpBasarili = {
  tur: "basarili" as const,
  config_json: '{\n  "mcpServers": {}\n}',
  yol: "/Users/x/grup54/.mcp.json",
  mod: "local" as const,
  araclar: mcpAraclar,
  hosted_notu: null,
};

afterEach(() => {
  vi.clearAllMocks();
});

describe("AyarlarPage — hosted gizleme (MUTASYON KİLİDİ)", () => {
  it("yükleniyorsa iskelet basar, yönlendirmez", () => {
    mockUseSaglayiciAyarlari.mockReturnValue({ data: undefined, isLoading: true });
    mockUseMcpConfig.mockReturnValue({ data: undefined, isLoading: true });
    renderPage();
    expect(screen.getByLabelText("Ayarlar yükleniyor")).toBeInTheDocument();
    expect(screen.queryByText("RADAR SAYFASI")).not.toBeInTheDocument();
  });

  it("GÖSTERİLECEK HİÇBİR ŞEY yoksa (iki uç da 'yok') sessizce /radar'a yönlendirir", () => {
    mockUseSaglayiciAyarlari.mockReturnValue({ data: { tur: "yok" }, isLoading: false });
    mockUseMcpConfig.mockReturnValue({ data: { tur: "yok" }, isLoading: false });
    renderPage();
    expect(screen.getByText("RADAR SAYFASI")).toBeInTheDocument();
    expect(screen.queryByText("Ayarlar")).not.toBeInTheDocument();
  });

  it("beklenmeyen hata verirse HataDurumu basar, sayfa çökmez", () => {
    mockUseSaglayiciAyarlari.mockReturnValue({
      data: { tur: "beklenmeyen", mesaj: "500 patladı" },
      isLoading: false,
    });
    mockUseMcpConfig.mockReturnValue({ data: { tur: "yok" }, isLoading: false });
    renderPage();
    expect(screen.getByText("Ayarlar alınamıyor")).toBeInTheDocument();
  });
});

describe("AyarlarPage — sağlayıcı formu render", () => {
  it("üç sağlayıcı da render olur, aktif olan Gemini işaretlenir", () => {
    mockUseSaglayiciAyarlari.mockReturnValue({ data: ayarBasarili, isLoading: false });
    mockUseMcpConfig.mockReturnValue({ data: mcpBasarili, isLoading: false });
    renderPage();
    expect(screen.getByRole("heading", { name: "Gemini" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Ollama (yerel)" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Groq (yedek)" })).toBeInTheDocument();
    expect(screen.getByText("Şu an aktif:")).toBeInTheDocument();
    expect(screen.getAllByText("aktif")).toHaveLength(1); // yalnız Gemini kartında
  });

  it("maskelenmiş anahtar YARDIMCI METİN olarak görünür, input DEĞERİ olarak DEĞİL (gerçek/maskeli anahtar hiçbir yerde input'ta değil)", () => {
    mockUseSaglayiciAyarlari.mockReturnValue({ data: ayarBasarili, isLoading: false });
    mockUseMcpConfig.mockReturnValue({ data: mcpBasarili, isLoading: false });
    renderPage();
    expect(screen.getByText(/kayıtlı: ANAH…4f2c/)).toBeInTheDocument();
    const geminiInput = screen.getAllByPlaceholderText("Değiştirmek için yeni anahtar gir")[0];
    expect(geminiInput).toHaveValue("");
  });

  it("Groq kartında 'aktif yap' YOK, yalnız 'Kaydet' butonu var (backend Groq'u aktif yapamaz)", () => {
    mockUseSaglayiciAyarlari.mockReturnValue({ data: ayarBasarili, isLoading: false });
    mockUseMcpConfig.mockReturnValue({ data: mcpBasarili, isLoading: false });
    renderPage();
    expect(
      screen.getByText(/Groq tek başına "aktif sağlayıcı" yapılamaz/),
    ).toBeInTheDocument();
    const groqKart = screen.getByRole("heading", { name: "Groq (yedek)" }).closest("div")!
      .parentElement!;
    expect(within(groqKart).getByRole("button", { name: "Kaydet" })).toBeInTheDocument();
    expect(within(groqKart).queryByRole("button", { name: /Aktif yap/ })).not.toBeInTheDocument();
  });
});

describe("AyarlarPage — anahtar kaydetme", () => {
  it("yeni anahtar girilip kaydedilince DOĞRU gövdeyle çağrılır, input SIFIRLANIR", async () => {
    mockUseSaglayiciAyarlari.mockReturnValue({ data: ayarBasarili, isLoading: false });
    mockUseMcpConfig.mockReturnValue({ data: mcpBasarili, isLoading: false });
    mockSaglayiciGuncelle.mockResolvedValue({
      tur: "basarili",
      mode: "local",
      saglayici: "gemini",
      anahtarlar: { gemini: "YENI…anah", groq: null },
      ollama_url: "http://localhost:11434",
    });
    const user = userEvent.setup();
    renderPage();

    const input = screen.getAllByPlaceholderText("Değiştirmek için yeni anahtar gir")[0];
    await user.type(input, "gercek-yeni-anahtar");
    // Gemini/Ollama kartlarının İKİSİ de "Aktif yap ve kaydet" der — Gemini
    // ÖNCE render olur (SaglayiciBolumu sırası), bu yüzden index 0.
    const butonlar = screen.getAllByRole("button", { name: "Aktif yap ve kaydet" });
    await user.click(butonlar[0]);

    expect(mockSaglayiciGuncelle).toHaveBeenCalledWith({
      saglayici: "gemini",
      anahtar: "gercek-yeni-anahtar",
    });
    expect(
      await screen.findByText("Kaydedildi — Gemini şimdi aktif sağlayıcı."),
    ).toBeInTheDocument();
    await waitFor(() => expect(input).toHaveValue(""));
  });

  it("input BOŞ bırakılırsa anahtar undefined gönderilir (mevcut anahtar KORUNUR, MUTASYON KİLİDİ)", async () => {
    mockUseSaglayiciAyarlari.mockReturnValue({ data: ayarBasarili, isLoading: false });
    mockUseMcpConfig.mockReturnValue({ data: mcpBasarili, isLoading: false });
    mockSaglayiciGuncelle.mockResolvedValue({ ...ayarBasarili });
    const user = userEvent.setup();
    renderPage();

    const butonlar = screen.getAllByRole("button", { name: "Aktif yap ve kaydet" });
    await user.click(butonlar[0]); // Gemini

    expect(mockSaglayiciGuncelle).toHaveBeenCalledWith({
      saglayici: "gemini",
      anahtar: undefined,
    });
  });

  it("422 dönerse backend'in mesajı AYNEN basılır", async () => {
    mockUseSaglayiciAyarlari.mockReturnValue({ data: ayarBasarili, isLoading: false });
    mockUseMcpConfig.mockReturnValue({ data: mcpBasarili, isLoading: false });
    mockSaglayiciGuncelle.mockResolvedValue({
      tur: "gecersiz",
      mesaj: "Ollama URL'i geçersiz — yalnız localhost/127.0.0.1 kabul edilir.",
    });
    const user = userEvent.setup();
    renderPage();
    const urlInput = screen.getByLabelText(/Sunucu adresi/);
    await user.clear(urlInput);
    await user.type(urlInput, "https://evil.example");
    const ollamaButonlar = screen.getAllByRole("button", { name: "Aktif yap ve kaydet" });
    await user.click(ollamaButonlar[1]);
    expect(
      await screen.findByText("Ollama URL'i geçersiz — yalnız localhost/127.0.0.1 kabul edilir."),
    ).toBeInTheDocument();
  });

  it("beklenmeyen bir hata verirse dürüst genel mesaj basılır, UYDURULMAZ", async () => {
    mockUseSaglayiciAyarlari.mockReturnValue({ data: ayarBasarili, isLoading: false });
    mockUseMcpConfig.mockReturnValue({ data: mcpBasarili, isLoading: false });
    mockSaglayiciGuncelle.mockResolvedValue({
      tur: "beklenmeyen",
      mesaj: "Kaydedilemedi — az sonra tekrar dene.",
    });
    const user = userEvent.setup();
    renderPage();
    const butonlar = screen.getAllByRole("button", { name: "Aktif yap ve kaydet" });
    await user.click(butonlar[0]); // Gemini
    expect(await screen.findByText("Kaydedilemedi — az sonra tekrar dene.")).toBeInTheDocument();
  });
});

describe("AyarlarPage — bağlantı testi (sahte-başarı YASAK, MUTASYON KİLİDİ)", () => {
  it("test BAŞARILI dönerse (calisiyor:true) backend'in mesajı basarili tonunda gösterilir", async () => {
    mockUseSaglayiciAyarlari.mockReturnValue({ data: ayarBasarili, isLoading: false });
    mockUseMcpConfig.mockReturnValue({ data: mcpBasarili, isLoading: false });
    mockSaglayiciTestEt.mockResolvedValue({
      tur: "sonuc",
      calisiyor: true,
      mesaj: "Bağlantı başarılı.",
    });
    const user = userEvent.setup();
    renderPage();
    const testButonlari = screen.getAllByRole("button", { name: "Bağlantıyı test et" });
    await user.click(testButonlari[0]); // Gemini
    expect(mockSaglayiciTestEt).toHaveBeenCalledWith("gemini");
    const mesaj = await screen.findByText("Bağlantı başarılı.");
    expect(mesaj).toBeInTheDocument();
  });

  it("test BAŞARISIZ dönerse (calisiyor:false) HATA GÖSTERİLİR — sahte başarı YOK", async () => {
    mockUseSaglayiciAyarlari.mockReturnValue({ data: ayarBasarili, isLoading: false });
    mockUseMcpConfig.mockReturnValue({ data: mcpBasarili, isLoading: false });
    mockSaglayiciTestEt.mockResolvedValue({
      tur: "sonuc",
      calisiyor: false,
      mesaj: "Gemini anahtarı geçersiz veya yetkisiz (401).",
    });
    const user = userEvent.setup();
    renderPage();
    const testButonlari = screen.getAllByRole("button", { name: "Bağlantıyı test et" });
    await user.click(testButonlari[0]);
    const mesaj = await screen.findByText("Gemini anahtarı geçersiz veya yetkisiz (401).");
    expect(mesaj).toBeInTheDocument();
    // "Bağlantı başarılı" gibi uydurma bir metin HİÇBİR YERDE basılmaz.
    expect(screen.queryByText(/başarılı/)).not.toBeInTheDocument();
  });

  it("Groq'un test butonu 'groq' argümanıyla çağrılır (kartın kendi sağlayıcısı)", async () => {
    mockUseSaglayiciAyarlari.mockReturnValue({ data: ayarBasarili, isLoading: false });
    mockUseMcpConfig.mockReturnValue({ data: mcpBasarili, isLoading: false });
    mockSaglayiciTestEt.mockResolvedValue({ tur: "sonuc", calisiyor: true, mesaj: "Bağlantı başarılı." });
    const user = userEvent.setup();
    renderPage();
    const testButonlari = screen.getAllByRole("button", { name: "Bağlantıyı test et" });
    await user.click(testButonlari[2]); // Groq üçüncü kart
    expect(mockSaglayiciTestEt).toHaveBeenCalledWith("groq");
  });
});

describe("AyarlarPage — AI aracına bağlanma (MCP) bölümü", () => {
  it("yapılandırma yüklenince İLK aracın yolu + parçacığı gösterilir", () => {
    mockUseSaglayiciAyarlari.mockReturnValue({ data: ayarBasarili, isLoading: false });
    mockUseMcpConfig.mockReturnValue({ data: mcpBasarili, isLoading: false });
    renderPage();
    expect(screen.getByText(/\/Users\/x\/grup54\/\.mcp\.json/)).toBeInTheDocument();
    expect(screen.getByText(/mcpServers/)).toBeInTheDocument();
  });

  it("başlık TEK bir aracı adlandırmaz + beş aracın hepsi seçilebilir (#332 MUTASYON KİLİDİ)", () => {
    // Bugünkü hata birebir buydu: başlık "Claude Code'a bağlan", tek yol.
    // `araclar.map(...)` yerine sabit tek bir araca dönersen → KIRMIZI.
    mockUseSaglayiciAyarlari.mockReturnValue({ data: ayarBasarili, isLoading: false });
    mockUseMcpConfig.mockReturnValue({ data: mcpBasarili, isLoading: false });
    renderPage();
    expect(screen.getByRole("heading", { name: "AI aracına bağlan (MCP)" })).toBeInTheDocument();
    const secici = screen.getByRole("group", { name: "AI aracı seç" });
    for (const a of mcpAraclar) {
      expect(within(secici).getByRole("button", { name: a.ad })).toBeInTheDocument();
    }
  });

  it("araç değişince YOL ve BİÇİM de değişir — Codex TOML gösterir (#332 MUTASYON KİLİDİ)", async () => {
    // Seçimi yok sayıp hep ilk aracın parçacığını basarsan → KIRMIZI. Bu,
    // "aynı JSON'ı beş araca da ver" hatasının UI tarafındaki kilidi.
    mockUseSaglayiciAyarlari.mockReturnValue({ data: ayarBasarili, isLoading: false });
    mockUseMcpConfig.mockReturnValue({ data: mcpBasarili, isLoading: false });
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole("button", { name: "Codex CLI" }));
    expect(screen.getByText(/~\/\.codex\/config\.toml/)).toBeInTheDocument();
    expect(screen.getByText(/mcp_servers\.ensemble/)).toBeInTheDocument();
    expect(screen.queryByText(/mcpServers/)).not.toBeInTheDocument();
  });

  it("paylaşımlı dosyada 'üzerine YAZMA' uyarısı çıkar, olmayanda ÇIKMAZ", async () => {
    mockUseSaglayiciAyarlari.mockReturnValue({ data: ayarBasarili, isLoading: false });
    mockUseMcpConfig.mockReturnValue({ data: mcpBasarili, isLoading: false });
    const user = userEvent.setup();
    renderPage();
    expect(screen.queryByText(/üzerine YAZMA/)).not.toBeInTheDocument(); // Claude Code
    await user.click(screen.getByRole("button", { name: "Codex CLI" }));
    expect(screen.getByText(/üzerine YAZMA/)).toBeInTheDocument(); // Codex config.toml
  });

  it("Kopyala tıklanınca panoya yazılır ve GEÇİCİ onay gösterilir", async () => {
    mockUseSaglayiciAyarlari.mockReturnValue({ data: ayarBasarili, isLoading: false });
    mockUseMcpConfig.mockReturnValue({ data: mcpBasarili, isLoading: false });
    // DİKKAT: `userEvent.setup()` jsdom'un KENDİ Clipboard stub'ını kurar/
    // sıfırlar — `Object.defineProperty` bundan ÖNCE çağrılırsa üzerine
    // yazılır. Bu yüzden mock, setup()'TAN SONRA tanımlanır.
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
    renderPage();
    await user.click(screen.getByRole("button", { name: "Kopyala" }));
    expect(writeText).toHaveBeenCalledWith(mcpAraclar[0].config_metni);
    expect(await screen.findByText("Kopyalandı ✓")).toBeInTheDocument();
  });

  it("sahte 'bağlandı' durumu YOK — yeniden başlatma uyarısı HER ZAMAN görünür (kopyalamadan ÖNCE de, MUTASYON KİLİDİ)", () => {
    mockUseSaglayiciAyarlari.mockReturnValue({ data: ayarBasarili, isLoading: false });
    mockUseMcpConfig.mockReturnValue({ data: mcpBasarili, isLoading: false });
    renderPage();
    expect(screen.queryByText(/bağlandı/i)).not.toBeInTheDocument();
    // Uyarı, bir "yeniden başlat" talimatı İÇEREN dürüstlük cümlesiyle birlikte
    // basılır — kopyalama eylemine bağlı DEĞİL, ilk render'da zaten görünür.
    expect(
      screen.getByText(/Bu sayfa bağlantının kurulduğunu DOĞRULAYAMAZ.*kendi aracında kontrol et/),
    ).toBeInTheDocument();
  });

  it("hosted'da SESSİZ 404 yok — sağlayıcı ucu yokken bile MCP gerekçesi + reçete basılır (#332 MUTASYON KİLİDİ)", () => {
    // Eski davranış: sağlayıcı 404 → sayfa /radar'a yönleniyordu, kullanıcı
    // MCP'yi hiç göremiyordu. `mcp?.tur !== "basarili"` koşulunu kaldırıp
    // eski koşulsuz Navigate'e dönersen → "RADAR SAYFASI" basılır → KIRMIZI.
    mockUseSaglayiciAyarlari.mockReturnValue({ data: { tur: "yok" }, isLoading: false });
    mockUseMcpConfig.mockReturnValue({
      data: {
        ...mcpBasarili,
        mod: "hosted" as const,
        hosted_notu: "MCP senin makinende bir stdio süreci olarak çalışır.",
      },
      isLoading: false,
    });
    renderPage();
    expect(screen.queryByText("RADAR SAYFASI")).not.toBeInTheDocument();
    expect(screen.getByText(/stdio süreci olarak çalışır/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "AI aracına bağlan (MCP)" })).toBeInTheDocument();
    // Sağlayıcı kartları hosted'da GÖRÜNMEZ (anahtarlar sunucunun).
    expect(screen.queryByRole("heading", { name: "Gemini" })).not.toBeInTheDocument();
  });

  it("İKİ uç da yoksa hâlâ /radar'a yönlendirir (ölü sayfa basma kuralı korunur)", () => {
    mockUseSaglayiciAyarlari.mockReturnValue({ data: { tur: "yok" }, isLoading: false });
    mockUseMcpConfig.mockReturnValue({ data: { tur: "yok" }, isLoading: false });
    renderPage();
    expect(screen.getByText("RADAR SAYFASI")).toBeInTheDocument();
  });

  it("MCP ucu yoksa (eski sunucu) bölüm çökmez, dürüstçe söyler", () => {
    mockUseSaglayiciAyarlari.mockReturnValue({ data: ayarBasarili, isLoading: false });
    mockUseMcpConfig.mockReturnValue({ data: { tur: "yok" }, isLoading: false });
    renderPage();
    expect(screen.getByText(/Bu sunucu sürümünde MCP ucu yok/)).toBeInTheDocument();
  });

  it("beklenmeyen hata verirse HataDurumu basılır", () => {
    mockUseSaglayiciAyarlari.mockReturnValue({ data: ayarBasarili, isLoading: false });
    mockUseMcpConfig.mockReturnValue({
      data: { tur: "beklenmeyen", mesaj: "500 patladı" },
      isLoading: false,
    });
    renderPage();
    expect(screen.getByText("MCP yapılandırması alınamıyor")).toBeInTheDocument();
  });
});
