"""`.harness/decisions/` — karar günlüğü ile README indeksi arasındaki drift kilidi.

Bu klasör **hesap verilebilirlik** için var: teslimde "neden böyle yapıldı"
sorusunun cevabı burada. Bir kayıt eklenip README'nin indeksi güncellenmezse,
public repo eksik/yanlış bir tablo gösterir — yani hesap verilebilirlik aracı
kendi kendine yalan söyler.

Bu repoda aynı desen 2026-07-27'de ALTI kez yakalandı (`deploy-runbook.md`
anahtar sayısı). Ortak ders: **iddia edilen sayıyı assert etme, gerçek sayıyı
SAY.** `assert len(x) == 3` yazan bir test dördüncü dosya eklenince kırılır ve
kimse nedenini anlamaz; burada README ile disk KARŞILAŞTIRILIYOR.
"""

import re
from pathlib import Path

_KOK = Path(__file__).resolve().parents[2]
_DIZIN = _KOK / ".harness" / "decisions"
_README = _DIZIN / "README.md"


def _karar_dosyalari() -> list[Path]:
    return sorted(p for p in _DIZIN.glob("D-*.md"))


def _readmede_listelenen_idler() -> set[str]:
    """README'nin 'Mevcut kayıtlar' tablosundaki `[D-NN](dosya)` bağlantıları."""
    metin = _README.read_text(encoding="utf-8")
    return set(re.findall(r"\[(D-\d+)\]\(D-\d+[^)]*\.md\)", metin))


def _dosyadaki_id(yol: Path) -> str | None:
    for satir in yol.read_text(encoding="utf-8").splitlines()[:12]:
        eslesme = re.match(r"^id:\s*(D-\d+)\s*$", satir)
        if eslesme:
            return eslesme.group(1)
    return None


def test_readme_indeksi_diskle_ESIT():
    """MUTASYON KİLİDİ: yeni bir `D-NN-*.md` ekleyip README'yi güncellemeyi
    unut → kırmızı. Tersi de: README'de olmayan bir dosyaya link bırak → kırmızı.
    """
    diskteki = {_dosyadaki_id(p) for p in _karar_dosyalari()} - {None}
    listelenen = _readmede_listelenen_idler()

    eksik = diskteki - listelenen
    fazla = listelenen - diskteki
    assert not eksik, (
        f"README indeksinde OLMAYAN karar kaydı var: {sorted(eksik)} — "
        "public repo eksik tablo gösterir"
    )
    assert not fazla, (
        f"README diskte OLMAYAN kayda link veriyor: {sorted(fazla)} — "
        "kırık bağlantı"
    )


def test_dosya_adi_ile_frontmatter_idsi_UYUSUR():
    """`D-56-*.md` içinde `id: D-55` yazıyorsa audit izi kopar."""
    for yol in _karar_dosyalari():
        beklenen = yol.name.split("-", 2)[0] + "-" + yol.name.split("-")[1]
        gercek = _dosyadaki_id(yol)
        assert gercek == beklenen, (
            f"{yol.name}: dosya adı '{beklenen}' diyor ama front-matter '{gercek}'"
        )


def test_readme_BOS_iddiasini_tasimiyor_kayit_varken():
    """README uzun süre 'bu klasör BOŞ' diyordu (doğruydu). Kayıt geldiğinde
    o cümle kalırsa doküman okuyucuyu yanıltır — bu, kilidin asıl yakaladığı
    şeyin somut hâli."""
    if not _karar_dosyalari():
        return  # klasör gerçekten boşsa iddia doğru
    metin = _README.read_text(encoding="utf-8")
    assert "klasör bugün BOŞ" not in metin, (
        "README hâlâ 'bu klasör bugün BOŞ' diyor ama içinde kayıt var"
    )


def test_kararlar_append_only_ruhuna_uygun_ZORUNLU_alanlari_tasir():
    """Şema `type/id/title/date`'i zorunlu kılıyor (`decision.schema.json`);
    `harness_validate.py` bunu CI'da doğruluyor. Buradaki kontrol o kapının
    yerine geçmez — yalnız dosyanın hiç front-matter'sız eklenmesini erken
    yakalar (şema doğrulayıcı yalnız front-matter VARSA çalışır)."""
    for yol in _karar_dosyalari():
        metin = yol.read_text(encoding="utf-8")
        assert metin.startswith("---"), f"{yol.name}: front-matter yok"
        for alan in ("type:", "id:", "title:", "date:"):
            assert alan in metin.split("---", 2)[1], f"{yol.name}: '{alan}' eksik"
