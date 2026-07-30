/**
 * Onboarding sihirbazının (#340, §8.5) veri katmanı.
 *
 * Sözleşme (kanonik: `api/routers/onboarding.py` modül dokümanı):
 *   GET  /onboarding/durum   -> {mode, yazma_mumkun, yazma_kok, harness_var,
 *                                saglayici, ai_kullanilabilir, maks_bosluk_turu}
 *   POST /onboarding/sorular -> {sorular, tur, tur_bitti, eksikler}
 *   POST /onboarding/brief   -> {brief, eksikler, uyarilar, ai_kullanildi, degraded?}
 *   POST /onboarding/taslak  -> {taslak, degraded?}
 *   POST /onboarding/plan    -> SprintPlani            | 400
 *   POST /onboarding/uygula  -> YazmaSonucu | 403 | 404 | 409
 *
 * TASLAĞIN SAHİBİ İSTEMCİDİR: sunucu oturum tutmaz, her uç taslağın tamamını
 * alır ve döner. Bu yüzden burada `useQuery` değil düz `async` fonksiyonlar
 * var (tek istisna `/durum` — o gerçekten sunucu durumu). Sihirbaz adımları
 * kullanıcı eylemidir, poll edilecek bir kaynak değil.
 *
 * HTTP durumu -> `tur` eşlemesi `useSettings.ts`/`useAuth.ts` kalıbının
 * AYNISI; hiçbir fonksiyon fırlatmaz. openapi-fetch tuzağı burada da geçerli:
 * boş gövdeli non-ok yanıtta `error` `""` (falsy) olabilir -> HER YERDE
 * `response.status`'a bakılır.
 */

import { useQuery } from "@tanstack/react-query";
import type { components } from "../api/schema.d.ts";
import { api } from "./api";
import { backendMesaji } from "./useAuth";

/** Üretilen şemadaki opsiyonelliği KALDIRIR.
 *
 * Backend'de bu alanların hepsi `default_factory=list` ile ZORUNLU ve HER
 * ZAMAN dolu gelir; ama Pydantic bir `default` yayınladığı için OpenAPI onları
 * `required` işaretlemiyor -> üretilen TS'te `string[] | undefined` oluyorlar.
 * Elle tip yazmak (drift riski) yerine şemadan TÜRETİP opsiyonelliği burada
 * soyuyoruz; alan adı/tipi değişirse derleme yine kırılır (kontrat kilidi
 * korunur), yalnız "undefined olabilir" gürültüsü sayfaya sızmaz. Değerler
 * `*Normalle()` fonksiyonlarında GERÇEKTEN dolduruluyor — tip yalanı değil. */
type Zorunlu<T> = { [K in keyof T]-?: Exclude<T[K], undefined> };

export type Eksik = Zorunlu<components["schemas"]["Eksik"]>;
export type Uyari = Zorunlu<components["schemas"]["Uyari"]>;
export type Soru = Zorunlu<components["schemas"]["Soru"]>;
export type Varsayim = Zorunlu<components["schemas"]["Varsayim"]>;
export type Kisitlar = Zorunlu<components["schemas"]["Kisitlar"]>;
export type Brief = Omit<
  Zorunlu<components["schemas"]["Brief"]>,
  "kisitlar" | "varsayimlar"
> & { kisitlar: Kisitlar; varsayimlar: Varsayim[] };
export type Epic = Zorunlu<components["schemas"]["Epic"]>;
export type UserStory = Zorunlu<components["schemas"]["UserStory"]>;
export type DusenStory = Zorunlu<components["schemas"]["DusenStory"]>;
export type StoryTaslagi = {
  epicler: Epic[];
  storyler: UserStory[];
  dusenler: DusenStory[];
};
export type SprintDilimi = Zorunlu<components["schemas"]["SprintDilimi"]>;
export type SprintPlani = {
  dilimler: SprintDilimi[];
  toplam_puan: number;
  uyarilar: string[];
};
export type OnboardingDurum = components["schemas"]["OnboardingDurum"];
export type OnboardingDegraded = components["schemas"]["OnboardingDegraded"];
export type YazmaSonucu = Zorunlu<components["schemas"]["YazmaSonucu"]>;
export type Mod = components["schemas"]["SorularIstegi"]["mod"];

type HamBrief = components["schemas"]["Brief"];
type HamTaslak = components["schemas"]["StoryTaslagi"];
type HamPlan = components["schemas"]["SprintPlani"];

function briefeNormalle(ham: HamBrief): Brief {
  return {
    urun_tek_cumle: ham.urun_tek_cumle ?? "",
    hedef_kullanicilar: ham.hedef_kullanicilar ?? [],
    cekirdek_ozellikler: ham.cekirdek_ozellikler ?? [],
    kapsam_disi: ham.kapsam_disi ?? [],
    kisitlar: {
      ekip_buyuklugu: ham.kisitlar?.ekip_buyuklugu ?? null,
      yetkinlikler: ham.kisitlar?.yetkinlikler ?? [],
      sprint_sayisi: ham.kisitlar?.sprint_sayisi ?? null,
      sprint_gun: ham.kisitlar?.sprint_gun ?? null,
      teknolojiler: ham.kisitlar?.teknolojiler ?? [],
      entegrasyonlar: ham.kisitlar?.entegrasyonlar ?? [],
    },
    basari_hedefi: ham.basari_hedefi ?? "",
    varsayimlar: ham.varsayimlar ?? [],
  };
}

function taslagaNormalle(ham: HamTaslak): StoryTaslagi {
  return {
    epicler: (ham.epicler ?? []).map((e) => ({
      id: e.id,
      baslik: e.baslik,
      aciklama: e.aciklama ?? "",
    })),
    storyler: (ham.storyler ?? []).map((s) => ({
      ...s,
      kabul_kriterleri: s.kabul_kriterleri ?? [],
      oncelik: s.oncelik ?? 3,
      bagimliliklar: s.bagimliliklar ?? [],
    })),
    dusenler: ham.dusenler ?? [],
  };
}

function planaNormalle(ham: HamPlan): SprintPlani {
  return {
    dilimler: (ham.dilimler ?? []).map((d) => ({
      ...d,
      story_idler: d.story_idler ?? [],
    })),
    toplam_puan: ham.toplam_puan,
    uyarilar: ham.uyarilar ?? [],
  };
}

export const BOS_BRIEF: Brief = {
  urun_tek_cumle: "",
  hedef_kullanicilar: [],
  cekirdek_ozellikler: [],
  kapsam_disi: [],
  kisitlar: {
    ekip_buyuklugu: null,
    yetkinlikler: [],
    sprint_sayisi: null,
    sprint_gun: null,
    teknolojiler: [],
    entegrasyonlar: [],
  },
  basari_hedefi: "",
  varsayimlar: [],
};

type Hata = { tur: "beklenmeyen"; mesaj: string };

export type SorularSonucu =
  | {
      tur: "basarili";
      sorular: Soru[];
      soruTuru: number;
      tur_bitti: boolean;
      eksikler: Eksik[];
    }
  | Hata;

export type BriefSonucu =
  | {
      tur: "basarili";
      brief: Brief;
      eksikler: Eksik[];
      uyarilar: Uyari[];
      ai_kullanildi: boolean;
      degraded: OnboardingDegraded | null;
    }
  | Hata;

export type TaslakSonucu =
  | { tur: "basarili"; taslak: StoryTaslagi; degraded: OnboardingDegraded | null }
  | Hata;

export type PlanSonucu = ({ tur: "basarili"; plan: SprintPlani }) | Hata;

export type UygulaSonucu =
  | ({ tur: "basarili" } & YazmaSonucu)
  /** 403 — K6: insan onayı olmadan yazma yok. Kullanıcıya AYNEN söylenir. */
  | { tur: "onaysiz"; mesaj: string }
  /** 404 — hosted kurulumda yazma adımı yoktur. */
  | { tur: "yok"; mesaj: string }
  /** 409 — hedef dosyalar zaten var; hiçbiri EZİLMEDİ. */
  | { tur: "cakisma"; mesaj: string }
  | Hata;

/** `/onboarding/durum` — sayfa açılır açılmaz "bu kurulumda ne yapabilirim". */
export function useOnboardingDurum() {
  return useQuery({
    queryKey: ["onboarding", "durum"],
    queryFn: async () => {
      const { data, error, response } = await api.GET("/onboarding/durum");
      if (error === undefined || error === null) {
        if (!data) return { tur: "beklenmeyen", mesaj: "Sunucu boş yanıt döndü." } as const;
        return { tur: "basarili", ...data } as const;
      }
      return {
        tur: "beklenmeyen",
        mesaj: backendMesaji(
          error,
          `Sihirbaz durumu alınamadı (HTTP ${response.status}).`,
        ),
      } as const;
    },
  });
}

export async function sorulariGetir(govde: {
  mod: Mod;
  tur: number;
  brief: Brief;
}): Promise<SorularSonucu> {
  try {
    const { data, error, response } = await api.POST("/onboarding/sorular", {
      body: govde,
    });
    if ((error === undefined || error === null) && data) {
      return {
        tur: "basarili",
        sorular: (data.sorular ?? []).map((s) => ({ ...s, coklu: s.coklu ?? false })),
        soruTuru: data.tur,
        tur_bitti: data.tur_bitti,
        eksikler: data.eksikler ?? [],
      };
    }
    return {
      tur: "beklenmeyen",
      mesaj: backendMesaji(error, `Sorular alınamadı (HTTP ${response.status}).`),
    };
  } catch (hata) {
    return { tur: "beklenmeyen", mesaj: agHatasi(hata) };
  }
}

export async function briefUret(govde: {
  mod: Mod;
  serbest_metin?: string;
  cevaplar?: Record<string, string>;
  brief: Brief;
  varsayimlarla_doldur?: boolean;
}): Promise<BriefSonucu> {
  try {
    const { data, error, response } = await api.POST("/onboarding/brief", {
      body: {
        mod: govde.mod,
        serbest_metin: govde.serbest_metin ?? "",
        cevaplar: govde.cevaplar ?? {},
        brief: govde.brief,
        varsayimlarla_doldur: govde.varsayimlarla_doldur ?? false,
      },
    });
    if ((error === undefined || error === null) && data) {
      return {
        tur: "basarili",
        brief: briefeNormalle(data.brief),
        eksikler: data.eksikler ?? [],
        uyarilar: data.uyarilar ?? [],
        ai_kullanildi: data.ai_kullanildi,
        degraded: data.degraded ?? null,
      };
    }
    return {
      tur: "beklenmeyen",
      mesaj: backendMesaji(error, `Brief üretilemedi (HTTP ${response.status}).`),
    };
  } catch (hata) {
    return { tur: "beklenmeyen", mesaj: agHatasi(hata) };
  }
}

export async function taslakUret(brief: Brief): Promise<TaslakSonucu> {
  try {
    const { data, error, response } = await api.POST("/onboarding/taslak", {
      body: { brief },
    });
    if ((error === undefined || error === null) && data) {
      return {
        tur: "basarili",
        taslak: taslagaNormalle(data.taslak),
        degraded: data.degraded ?? null,
      };
    }
    return {
      tur: "beklenmeyen",
      mesaj: backendMesaji(error, `Taslak üretilemedi (HTTP ${response.status}).`),
    };
  } catch (hata) {
    return { tur: "beklenmeyen", mesaj: agHatasi(hata) };
  }
}

export async function planUret(govde: {
  storyler: UserStory[];
  kapasite: { ekip_buyuklugu: number; sprint_sayisi: number; musaitlik?: number[] | null };
}): Promise<PlanSonucu> {
  try {
    const { data, error, response } = await api.POST("/onboarding/plan", { body: govde });
    if ((error === undefined || error === null) && data) {
      return { tur: "basarili", plan: planaNormalle(data) };
    }
    return {
      tur: "beklenmeyen",
      mesaj: backendMesaji(error, `Sprint planı üretilemedi (HTTP ${response.status}).`),
    };
  } catch (hata) {
    return { tur: "beklenmeyen", mesaj: agHatasi(hata) };
  }
}

export async function uygula(govde: {
  onay: { onaylandi: boolean; onaylayan: string };
  brief: Brief;
  taslak: StoryTaslagi;
  plan?: SprintPlani | null;
}): Promise<UygulaSonucu> {
  try {
    const { data, error, response } = await api.POST("/onboarding/uygula", {
      body: govde,
    });
    if ((error === undefined || error === null) && data) {
      return {
        tur: "basarili",
        yazilan: data.yazilan ?? [],
        sprint_dosyalari: data.sprint_dosyalari ?? [],
        task_dosyalari: data.task_dosyalari ?? [],
        kok: data.kok ?? "",
      };
    }
    // 403/404/409 AYRI AYRI karşılanır: üçü de "olmadı" ama kullanıcının
    // yapacağı şey farklı (onay kutusunu işaretle / local'de aç / dosyaları
    // temizle). Tek bir "hata oldu" mesajı bu farkı yok ederdi.
    if (response.status === 403) {
      return {
        tur: "onaysiz",
        mesaj: backendMesaji(error, "İnsan onayı olmadan diske yazılmaz (K6)."),
      };
    }
    if (response.status === 404) {
      return {
        tur: "yok",
        mesaj: backendMesaji(
          error,
          "Bu kurulumda yazma adımı yok — sihirbaz yalnız local kurulumda .harness/ yazar.",
        ),
      };
    }
    if (response.status === 409) {
      return {
        tur: "cakisma",
        mesaj: backendMesaji(error, "Hedef dosyalar zaten var; hiçbiri değiştirilmedi."),
      };
    }
    return {
      tur: "beklenmeyen",
      mesaj: backendMesaji(error, `Yazma başarısız (HTTP ${response.status}).`),
    };
  } catch (hata) {
    return { tur: "beklenmeyen", mesaj: agHatasi(hata) };
  }
}

function agHatasi(hata: unknown): string {
  const detay = hata instanceof Error ? hata.message : String(hata);
  return `Backend'e ulaşılamadı — bağlantıyı ve VITE_API_BASE_URL'i kontrol et. (${detay})`;
}

/** Çok satırlı metin alanı <-> string[] dönüşümü (formun tek yerdeki kuralı). */
export function satirlaraBol(metin: string): string[] {
  return metin
    .split("\n")
    .map((s) => s.replace(/^[-•*]\s*/, "").trim())
    .filter((s) => s.length > 0);
}

export function satirlariBirlestir(liste: string[]): string {
  return liste.join("\n");
}
