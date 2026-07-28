/** ActorChip — aktör doğrulama göstergesi (#296, T-296).
 *
 * #296 teşhisi: ingest, commit yazarını GitHub hesabıyla (author.login /
 * webhook author.username) eşleştiremediğinde ham git commit adına düşer
 * ("Merge Simulation" vakası) — bu düşüş bugüne kadar arayüzde GÖRÜNMEZDİ.
 * `ActorChip` artık opsiyonel bir `verified` prop'u alır; `false` verilince
 * renk TEK BAŞINA değil (D-34, #293 AA kontrast dersi), İKİ ayrı sinyal +
 * title metniyle "bu commit'in e-postası bir GitHub hesabıyla eşleşmedi"
 * der (uydurma yok — "sahte kişi" DENMEZ).
 *
 * Mutasyon kilitleri (bu dosyada, elle KOŞULUP kırmızı olduğu doğrulanmış,
 * PR gövdesine tablo halinde işlenmiştir):
 *   (a) `verified` prop'unu YOK SAY (hep doğrulanmış render et) → rozet
 *       testi kırmızı.
 *   (b) varsayılanı ters çevir (`verified = false` yap) → varsayılan-doğrulanmış
 *       testi kırmızı.
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { ActorChip } from "../src/components/ui";

function wrapper(children: React.ReactNode) {
  return <MemoryRouter>{children}</MemoryRouter>;
}

describe("ActorChip — verified göstergesi (#296)", () => {
  it("verified=true (açık): rozet YOK, title değişmez", () => {
    render(wrapper(<ActorChip handle="esma6" verified />));
    expect(screen.queryByTestId("actor-unverified-badge")).toBeNull();
    expect(screen.getByTitle("esma6")).toBeInTheDocument();
  });

  it("verified belirtilmemiş (varsayılan): DOĞRULANMIŞ sayılır — rozet YOK", () => {
    // MUTASYON KİLİDİ: varsayılan `true` -> `false` yapılırsa bu test kırılır
    // (eski/veri taşımayan HER çağıran sessizce "eşleşmedi" görünür).
    render(wrapper(<ActorChip handle="esma6" />));
    expect(screen.queryByTestId("actor-unverified-badge")).toBeNull();
    expect(screen.getByTitle("esma6")).toBeInTheDocument();
  });

  it("verified=false: rozet GÖRÜNÜR + title 'eşleşmedi' der (uydurma yok)", () => {
    // MUTASYON KİLİDİ: ActorChip gövdesinden `eslesmedi` dalı SİLİNİRSE
    // (hep doğrulanmış render edilirse) bu test kırılır.
    render(wrapper(<ActorChip handle="Merge Simulation" verified={false} />));
    expect(screen.getByTestId("actor-unverified-badge")).toBeInTheDocument();
    const baslik = screen.getByTitle(/Merge Simulation/);
    expect(baslik.getAttribute("title")).toContain("eşleşmedi");
    // Uydurma yasak: "sahte"/"gerçek değil" gibi bir suçlama YOK.
    expect(baslik.getAttribute("title")).not.toMatch(/sahte|gerçek değil/i);
  });

  it("verified=false + type=agent: kare avatar + rozet BİRLİKTE (şekil ayrımı korunur)", () => {
    render(wrapper(<ActorChip handle="fatih-claude" type="agent" verified={false} />));
    expect(screen.getByTestId("actor-unverified-badge")).toBeInTheDocument();
    expect(screen.getByTitle(/fatih-claude \(AI ajanı\) — /)).toBeInTheDocument();
  });

  it("linkli + verified=false: link'e giden title AYNI eşleşmedi metnini taşır", () => {
    render(wrapper(<ActorChip handle="Merge Simulation" linkli verified={false} />));
    const link = screen.getByRole("link");
    expect(link.getAttribute("title")).toContain("eşleşmedi");
    expect(screen.getByTestId("actor-unverified-badge")).toBeInTheDocument();
  });
});
