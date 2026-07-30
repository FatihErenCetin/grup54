"""Onaylanmış taslağı `.harness/`'e yazan TEK kapı (#340, §8.5 adım 5).

**K6 — KİLİTLİ KURAL: AI taslaklar, İNSAN onaylar.** Bu modül o kuralın
uygulanan hâlidir; sihirbazın diske değen tek noktası burasıdır. Sözleşme üç
maddede:

  1. `onay.onaylandi is not True` -> `OnaysizYazmaHatasi`. Kontrol fonksiyonun
     İLK satırındadır: `mkdir` bile çağrılmaz, yani reddedilen bir istek
     `.harness/` dizinini var etmez (yarım iskelet, `wizard.init_harness`'in
     "zaten var -> dokunma" fail-safe'ini yanlış tetiklerdi — #57 review'ünde
     ölçülen sınıfın aynısı).
  2. Var olan hiçbir dosyanın ÜZERİNE yazılmaz. Bir sihirbaz taslağının PO'nun
     dondurduğu `scope/sprint-N.md`'yi ezmesi geri alınamaz bir veri kaybıdır;
     çakışma tespit edilirse `MevcutDosyaHatasi` ile dosya ADLARI listelenir.
  3. Yazma ATOMİK DEĞİL ama SIRALI ve raporludur: ne yazıldıysa dönen listede
     görünür. Yarıda hata olursa yazılanlar durur (silinmez) — kullanıcı neyin
     yazıldığını cevaptan görür ve elle temizler. Sessizce geri sarmak, K6'nın
     "her çıktı düzenlenebilir taslaktır" ilkesiyle çelişirdi.

Neden `wizard.init_harness` yetmiyor: o, tek seferlik `.harness/` iskeletini
(gh issue -> md aynası) kurar ve `.harness/` VARSA hiç çalışmaz. Bu modül ise
sihirbazın İNSAN ONAYLI çıktısını yazar; iskelet zaten kurulmuşsa da çalışması
gerekir (yalnız çakışan dosyaya dokunmaz).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from ensemble.onboarding.intake import Brief, alan_adi
from ensemble.onboarding.sprint_plan import SprintPlani
from ensemble.onboarding.story import StoryTaslagi, UserStory

# wizard.py'nin iskelet parçaları BİLEREK yeniden yazılmıyor: `.harness/`
# README'si ve boş kategori dizinleri tek kaynaktan gelmeli, yoksa iki
# onboarding yolu iki farklı iskelet kurar (aynı repoda çelişki).
from ensemble.onboarding.wizard import _HARNESS_README, _write_empty_categories
from ensemble_shared.harness import FileHarnessPort, HarnessPort

_TASK_NO_RE = re.compile(r"^T-(\d+)")


class OnaysizYazmaHatasi(RuntimeError):
    """İnsan onayı olmadan diske yazma girişimi (K6 ihlali)."""


class MevcutDosyaHatasi(RuntimeError):
    """Hedef dosyalar zaten var — üzerine yazmayı REDDEDİYORUZ."""


class OnayKaydi(BaseModel):
    """İnsan onayının kaydı. `onaylandi` tek başına yeterli DEĞİL: kimin
    onayladığı da yazılır — `.harness/` bir denetim (audit) yüzeyidir ve
    "bu kapsamı kim dondurdu" sorusunun cevabı dosyada durmalı."""

    onaylandi: bool = False
    onaylayan: str = ""


class YazmaSonucu(BaseModel):
    yazilan: list[str] = Field(default_factory=list)
    sprint_dosyalari: list[str] = Field(default_factory=list)
    task_dosyalari: list[str] = Field(default_factory=list)
    kok: str = ""
    # #340: board bir DB PROJEKSIYONUdur, `.harness/`i canli okumaz. Yazmadan
    # sonra projeksiyon tazelenmezse kullanici "yazdi ama hicbir sey olmadi"
    # gorur. Bu alanlar o adimin SONUCUNU tasir — sessiz gecmez:
    #   projeksiyon_eklenen = kac kart acildi (None = hic denenemedi)
    #   projeksiyon_notu     = denenemediyse NEDEN (kullaniciya gosterilir)
    projeksiyon_eklenen: int | None = None
    projeksiyon_notu: str | None = None


def _sonraki_task_no(root: Path) -> int:
    """Mevcut `tasks/` dosyalarındaki en büyük numaranın bir fazlası.

    Greenfield'da 1'den başlar. Brownfield'da (bu repo gibi, task id'leri
    GitHub issue numarası) mevcut numaraların ÜSTÜNDEN devam eder — aksi halde
    `T-1` çakışır ve (2) kuralı gereği yazma tamamen reddedilirdi.
    """
    tasks_dir = root / ".harness" / "tasks"
    if not tasks_dir.is_dir():
        return 1
    numaralar = [
        int(m.group(1))
        for path in tasks_dir.glob("*.md")
        if (m := _TASK_NO_RE.match(path.name))
    ]
    return max(numaralar, default=0) + 1


def _sprint_dosya_adi(sprint_no: int) -> str:
    return f"sprint-{sprint_no}"


def _story_gorunum(story: UserStory) -> str:
    return story.olarak_cumle()


def _brief_govdesi(brief: Brief, plan: SprintPlani | None, sprint_no: int | None) -> str:
    """Kapsam belgesinin insan gövdesi — taslak olduğunu AÇIKÇA söyler."""
    satirlar = [
        "[TASLAK — onboarding sihirbazı üretti, insan onayladı; PO düzenleyip dondurur]",
        "",
        f"**Ürün:** {brief.urun_tek_cumle or '(belirtilmedi)'}",
        f"**Hedef kullanıcılar:** {', '.join(brief.hedef_kullanicilar) or '(belirtilmedi)'}",
        f"**Başarı/demo hedefi:** {brief.basari_hedefi or '(belirtilmedi)'}",
    ]
    kisit = brief.kisitlar
    kisit_parcalari = []
    if kisit.ekip_buyuklugu:
        kisit_parcalari.append(f"{kisit.ekip_buyuklugu} kişi")
    if kisit.sprint_sayisi:
        kisit_parcalari.append(f"{kisit.sprint_sayisi} sprint")
    if kisit.teknolojiler:
        kisit_parcalari.append("teknoloji: " + ", ".join(kisit.teknolojiler))
    if kisit.entegrasyonlar:
        kisit_parcalari.append("entegrasyon: " + ", ".join(kisit.entegrasyonlar))
    if kisit_parcalari:
        satirlar.append(f"**Kısıtlar:** {' · '.join(kisit_parcalari)}")

    if plan is not None and sprint_no is not None:
        dilim = next((d for d in plan.dilimler if d.sprint == sprint_no), None)
        if dilim is not None:
            satirlar += [
                "",
                f"**Kapasite bütçesi:** {dilim.yuk}/{dilim.butce} puan "
                f"({len(dilim.story_idler)} story)",
            ]

    if brief.varsayimlar:
        # Varsayımlar dosyaya YAZILIR: onaydan sonra bile "bunu kim söyledi"
        # sorusunun cevabı kaybolmamalı (kabul kriteri: varsayımlar işaretli).
        satirlar += ["", "**AI varsayımları (kullanıcı doğrulamalı):**"]
        satirlar += [
            f"- `{alan_adi(v.alan)}` — {v.deger_ozeti} _( {v.gerekce} )_"
            for v in brief.varsayimlar
        ]
    return "\n".join(satirlar) + "\n"


def _task_govdesi(story: UserStory, sprint_no: int | None) -> str:
    satirlar = [
        "[TASLAK — onboarding sihirbazı üretti, insan onayladı]",
        "",
        _story_gorunum(story),
        "",
        f"**Puan:** {story.puan} · **Öncelik:** {story.oncelik}"
        + (f" · **Sprint:** {sprint_no}" if sprint_no else ""),
    ]
    if story.kabul_kriterleri:
        satirlar += ["", "**Kabul kriterleri:**"]
        satirlar += [f"- [ ] {k}" for k in story.kabul_kriterleri]
    if story.bagimliliklar:
        satirlar += ["", f"**Bağımlılıklar:** {', '.join(story.bagimliliklar)}"]
    return "\n".join(satirlar) + "\n"


def _cakisan_dosyalar(root: Path, sprintler: list[int], task_adlari: list[str]) -> list[str]:
    harness = root / ".harness"
    cakisan: list[str] = []
    for no in sprintler:
        yol = harness / "scope" / f"{_sprint_dosya_adi(no)}.md"
        if yol.exists():
            cakisan.append(f"scope/{yol.name}")
    tasks_dir = harness / "tasks"
    if tasks_dir.is_dir():
        # `_sonraki_task_no` zaten mevcut en büyük numaranın üstünden devam
        # ediyor, yani burada normalde çakışma ÇIKMAZ. Kontrol yine de var:
        # numaralandırma mantığı ileride değişirse sessizce dosya ezmek yerine
        # gürültülü şekilde durmasını istiyoruz (savunma katmanı).
        mevcut = {
            f"T-{m.group(1)}"
            for p in tasks_dir.glob("T-*.md")
            if (m := _TASK_NO_RE.match(p.name))
        }
        for task_id in task_adlari:
            if task_id in mevcut:
                cakisan.append(f"tasks/{task_id}-*.md")
    return cakisan


def harness_yaz(
    root: Path | str,
    *,
    brief: Brief,
    taslak: StoryTaslagi,
    plan: SprintPlani | None,
    onay: OnayKaydi,
    harness_port: HarnessPort | None = None,
) -> YazmaSonucu:
    """Onaylanmış sihirbaz çıktısını `.harness/`'e yazar.

    ⚠️ K6 KAPISI — bu fonksiyonun İLK satırı onay kontrolüdür. Kaldırılırsa
    `tests/unit/test_onboarding_onay_kapisi.py` düşer (mutasyonla doğrulandı).
    """
    if onay.onaylandi is not True:
        # Fail-closed: "onay yok" bir DEĞER değil, bir HATA. Sessizce boş bir
        # sonuç dönmek (fail-open) çağıranın "yazıldı" sanmasına yol açardı.
        raise OnaysizYazmaHatasi(
            "İnsan onayı olmadan .harness/ yazılamaz (K6). Hiçbir dosyaya dokunulmadı."
        )

    root = Path(root)
    port = harness_port or FileHarnessPort(root)

    # Story -> sprint eşlemesi (plan varsa). Plan yoksa hepsi tek belgeye.
    story_sprinti: dict[str, int] = {}
    if plan is not None:
        for dilim in plan.dilimler:
            for story_id in dilim.story_idler:
                story_sprinti[story_id] = dilim.sprint

    sprintler = sorted({*story_sprinti.values()}) or [1]

    baslangic = _sonraki_task_no(root)
    task_idleri = {
        story.id: f"T-{baslangic + i}" for i, story in enumerate(taslak.storyler)
    }

    cakisan = _cakisan_dosyalar(root, sprintler, list(task_idleri.values()))
    if cakisan:
        raise MevcutDosyaHatasi(
            "Şu dosyalar zaten var, üzerine yazılmadı: " + ", ".join(sorted(cakisan))
        )

    sonuc = YazmaSonucu(kok=str(root))

    # 1) Kapsam belgeleri — sprint başına bir tane.
    for sprint_no in sprintler:
        sprint_storyleri = [
            s for s in taslak.storyler if story_sprinti.get(s.id, 1) == sprint_no
        ]
        hedefler = [_story_gorunum(s) for s in sprint_storyleri] or list(
            brief.cekirdek_ozellikler
        )
        port.write_scope(
            _sprint_dosya_adi(sprint_no),
            {
                "title": f"Sprint {sprint_no}",
                "status": "draft",
                "owner": onay.onaylayan or "bilinmiyor",
                "frozen_at": datetime.now(timezone.utc).isoformat(),
                "goals": hedefler,
                "non_goals": list(brief.kapsam_disi),
                "body": _brief_govdesi(brief, plan, sprint_no),
            },
        )
        ad = f"scope/{_sprint_dosya_adi(sprint_no)}.md"
        sonuc.sprint_dosyalari.append(ad)
        sonuc.yazilan.append(ad)

    # 2) Görev dosyaları — story başına bir tane (board'ın kanonik kaydı).
    for story in taslak.storyler:
        task_id = task_idleri[story.id]
        port.write_task(
            task_id,
            {
                "title": _story_gorunum(story),
                "status": "backlog",
                "assignee": None,
                "paths": [],
                "body": _task_govdesi(story, story_sprinti.get(story.id)),
            },
        )
        ad = f"tasks/{task_id}-*.md"
        sonuc.task_dosyalari.append(ad)
        sonuc.yazilan.append(ad)

    # 3) İskeletin kalanı — YALNIZ eksikse (var olanı ezmez).
    sonuc.yazilan += _write_empty_categories(root)
    readme = root / ".harness" / "README.md"
    if not readme.exists():
        readme.write_text(_HARNESS_README, encoding="utf-8")
        sonuc.yazilan.append(".harness/README.md")

    return sonuc
