/** Sidebar ikonları (#316/A2) — Pencil karşılaştırması: sidebar öğelerinin
    hiçbirinde ikon yoktu, yalnız metin. Altısı da elle çizilmiş inline SVG:
    16px, `stroke="currentColor"` (NavLink'in kendi metin rengini devralır,
    aktif/pasif için AYRI bir renk sınıfı gerekmez) — yeni bir ikon kütüphanesi
    KURULMADI (bağımlılık yasağı, bkz. #130 GraphPage notu). Dekoratif
    (`aria-hidden`): erişilebilirlik adı NavLink'in kendi metninden gelir,
    ikon tekrar okunmasın diye.

    Ayarlar (T-309, koşullu 7. kalem) Pencil karşılaştırmasında yoktu ama aynı
    sidebar'da ikonsuz tek kalem bırakmak tutarsız görünürdü — SettingsIcon
    aynı gerekçeyle eklendi. */

type IconProps = { className?: string };

const ORTAK = {
  width: 16,
  height: 16,
  viewBox: "0 0 16 16",
  fill: "none" as const,
  stroke: "currentColor",
  strokeWidth: 1.5,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true as const,
};

/** Radar — konsantrik tarama halkaları + merkezden dışa tek bir tarama kolu. */
export function RadarIcon({ className }: IconProps) {
  return (
    <svg {...ORTAK} className={className}>
      <circle cx="8" cy="8" r="6" />
      <circle cx="8" cy="8" r="3.2" />
      <circle cx="8" cy="8" r="0.9" fill="currentColor" stroke="none" />
      <path d="M8 8 12.6 3.6" />
    </svg>
  );
}

/** Board — farklı yükseklikte üç kolon (kanban: backlog/in-progress/done). */
export function BoardIcon({ className }: IconProps) {
  return (
    <svg {...ORTAK} className={className}>
      <rect x="1.6" y="3" width="3.2" height="10" rx="0.8" />
      <rect x="6.4" y="3" width="3.2" height="6.4" rx="0.8" />
      <rect x="11.2" y="3" width="3.2" height="10" rx="0.8" />
    </svg>
  );
}

/** Scope — hedef tabelası (crosshair): radar'dan FARKLI olsun diye tarama
    kolu yerine dört yönlü çizgi kullanıldı ("sınırı işaretle" imgesi). */
export function ScopeIcon({ className }: IconProps) {
  return (
    <svg {...ORTAK} className={className}>
      <circle cx="8" cy="8" r="6" />
      <path d="M8 1v2.6M8 12.4V15M1 8h2.6M12.4 8H15" />
      <circle cx="8" cy="8" r="1" fill="currentColor" stroke="none" />
    </svg>
  );
}

/** Graf — üç düğüm + kenarlar (dokunma grafının kendisiyle aynı dil: node-link). */
export function GraphIcon({ className }: IconProps) {
  return (
    <svg {...ORTAK} className={className}>
      <path d="M4.8 4.6 11.2 4.6M4.1 5.4 7.5 11.4M11.9 5.4 8.5 11.4" />
      <circle cx="3.6" cy="4" r="1.8" fill="currentColor" stroke="none" />
      <circle cx="12.4" cy="4" r="1.8" fill="currentColor" stroke="none" />
      <circle cx="8" cy="12.6" r="1.8" fill="currentColor" stroke="none" />
    </svg>
  );
}

/** Activity — nabız/EKG çizgisi (olay akışının "canlı" hissi). */
export function ActivityIcon({ className }: IconProps) {
  return (
    <svg {...ORTAK} className={className}>
      <path d="M1 8.5h2.6l1.5-5.2 2.4 9.4 1.8-7 1.1 2.8H15" />
    </svg>
  );
}

/** Ask — konuşma balonu + soru işareti (doğal dille "projeye sor"). */
export function AskIcon({ className }: IconProps) {
  return (
    <svg {...ORTAK} className={className}>
      <path d="M2 3.6c0-.77.63-1.4 1.4-1.4h9.2c.77 0 1.4.63 1.4 1.4v6.4c0 .77-.63 1.4-1.4 1.4H6.2L3 14.4v-3H3.4A1.4 1.4 0 0 1 2 10Z" />
      <path d="M6.3 5.9a1.75 1.75 0 1 1 2.5 1.6c-.6.3-.85.6-.85 1.2" />
      <circle cx="8" cy="10.6" r="0.6" fill="currentColor" stroke="none" />
    </svg>
  );
}

/** Ayarlar — basit dişli (yalnız local'de koşullu görünen 7. kalem, T-309). */
export function SettingsIcon({ className }: IconProps) {
  return (
    <svg {...ORTAK} className={className}>
      <circle cx="8" cy="8" r="2.4" />
      <path d="M8 1.6v1.6M8 12.8v1.6M2.3 4.8l1.4.8M12.3 10.4l1.4.8M2.3 11.2l1.4-.8M12.3 5.6l1.4-.8M1.6 8h1.6M12.8 8h1.6" />
    </svg>
  );
}
