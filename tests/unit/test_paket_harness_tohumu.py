"""#340 doğrulama turu — masaüstü paketi BAŞKA bir projenin verisini tohumlamaz.

Ölçüm (30 Tem): `packaging/ensemble.spec` `REPO_ROOT/.harness`'i gömüyordu,
yani grup54'ün donmuş sprint kapsamı + 22 görev + karar kayıtları yeni
kullanıcının başlangıç durumu oluyordu. Ayrıca onboarding sihirbazı 3 sprintlik
plan yazarken `scope/sprint-3.md`'ye çarpıp TÜM yazmayı 409 ile kaybediyordu.

Bu bir konfigürasyon kilidi (`test_proxy_headers.py` ile aynı desen): kusur
kodda değil, paketleme tanımındaydı ve hiçbir davranış testi göremezdi.
"""

from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SPEC = _REPO / "packaging" / "ensemble.spec"
_TOHUM = _REPO / "packaging" / "harness_seed" / ".harness"


def test_spec_repo_kokundeki_harnessi_TOHUMLAMAZ() -> None:
    """MUTASYON KİLİDİ: spec'i `REPO_ROOT / ".harness"`e geri çevir → düşer."""
    metin = _SPEC.read_text(encoding="utf-8")
    tohum_satirlari = [
        s for s in metin.splitlines()
        if "harness_seed/.harness" in s and s.strip().startswith("datas.append")
    ]
    assert len(tohum_satirlari) == 1, "tek bir tohum girdisi bekleniyordu"
    satir = tohum_satirlari[0]
    assert "harness_seed" in satir.split(",")[0], (
        "tohum kaynağı packaging/harness_seed olmalı; repo kökündeki .harness "
        "gömülürse kullanıcı BAŞKA bir projenin kapsam/görev/karar dosyalarını "
        "kendi başlangıç durumu olarak görür"
    )


def test_tohum_iskeleti_acilis_kontrolunun_istedigi_klasorleri_tasir() -> None:
    """`_verify_harness_boot` scope/tasks/active'in OKUNABİLİR olmasını ister."""
    for klasor in ("scope", "tasks", "active"):
        assert (_TOHUM / klasor).is_dir(), f"tohumda {klasor}/ yok — açılış patlar"


def test_tohum_BOS_kalir_ornek_proje_verisi_TASIMAZ() -> None:
    """MUTASYON KİLİDİ: tohuma bir `scope/sprint-*.md` ya da `tasks/T-*.md`
    koy → düşer. Dolu tohum, sihirbazın yazmasını 409 ile bloklar."""
    kirletenler = [
        p.relative_to(_TOHUM).as_posix()
        for p in _TOHUM.rglob("*")
        if p.is_file() and p.name not in (".gitkeep", "README.md")
    ]
    assert not kirletenler, (
        "tohum boş kalmalı; bulunanlar sihirbazın ilk yazmasını 409'a "
        f"düşürür: {kirletenler}"
    )


@pytest.mark.parametrize("desen", ["scope/sprint-*.md", "tasks/T-*.md"])
def test_tohumda_grup54un_kendi_kayitlari_YOK(desen: str) -> None:
    assert not list(_TOHUM.glob(desen)), (
        f"tohumda {desen} var — bu grup54'ün kendi verisi, kullanıcının değil"
    )
