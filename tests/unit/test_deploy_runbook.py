"""Deploy runbook (#190) drift kilidi — sozlesme: docs/sprint3-kontratlar.md Ek A.

Amac: `.env.example`'a yeni bir anahtar eklenip `docs/deploy-runbook.md`
guncellenmezse CI kirmizi olsun (issue #190'in asil derdi olan drift). Ag yok,
deterministik; stdlib + pathlib disinda bagimlilik yok (mevcut
`test_error_envelope.py` vb. deseni izler — ayri bir fixture/mock katmani
gerektirmiyor).

Bilincli test EDILMEYEN: tablo satirlarinin markdown yapisini parse edip
"ayni anahtar iki sutunda" kuralini dogrulamak — kirilgan (bicim degisince
yanlis kirmizi), degeri dusuk. Insan review'una birakilir (docs/review-rehberi.md).
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_EXAMPLE = _REPO_ROOT / ".env.example"
_RUNBOOK = _REPO_ROOT / "docs" / "deploy-runbook.md"

# .env.example'daki duz "ANAHTAR=" satirlarini yakalar (yorum satirlari HARIC —
# CORS_ORIGINS bilerek bu regex'in disinda kaliyor, bkz. asagidaki ayri test).
_ENV_KEY_RE = re.compile(r"^([A-Z_][A-Z0-9_]*)=", re.MULTILINE)

# .env.example'da yalniz YORUM ornegi olarak gecen ama runbook'un yine de
# kapsamasi gereken anahtar (kabul kriteri: "her .env.example anahtari").
_COMMENT_ONLY_KEY = "CORS_ORIGINS"


def _env_example_keys() -> list[str]:
    text = _ENV_EXAMPLE.read_text(encoding="utf-8")
    return _ENV_KEY_RE.findall(text)


def _runbook_text() -> str:
    return _RUNBOOK.read_text(encoding="utf-8")


def test_env_example_anahtarlarinin_tamami_runbookta():
    keys = _env_example_keys()
    assert keys, ".env.example'da hic anahtar bulunamadi — regex/dosya yolu kontrol et"

    runbook = _runbook_text()
    eksik = [k for k in keys if k not in runbook]
    assert not eksik, (
        f"docs/deploy-runbook.md su .env.example anahtarlarini kapsamiyor: {eksik} "
        "(kabul kriteri 1 — Ek A/A1 tablosuna satir ekle)"
    )


def test_cors_origins_yorumlu_anahtar_da_kapsanir():
    # CORS_ORIGINS .env.example'da yalniz "# CORS_ORIGINS=..." yorum-ornegi
    # olarak gecer -> duz-satir regex'i onu YAKALAMAZ. Runbook yine de bu
    # anahtari kapsamak zorunda (kabul kriteri 1); burada acikca iddia edilir
    # ki sessiz bosluk kalmasin.
    env_text = _ENV_EXAMPLE.read_text(encoding="utf-8")
    assert _COMMENT_ONLY_KEY not in _ENV_KEY_RE.findall(env_text), (
        f"{_COMMENT_ONLY_KEY} artik duz satir olarak geciyor gibi gorunuyor — "
        "bu testin varsayimini guncelle"
    )
    assert f"# {_COMMENT_ONLY_KEY}=" in env_text or f"#{_COMMENT_ONLY_KEY}=" in env_text

    runbook = _runbook_text()
    assert _COMMENT_ONLY_KEY in runbook, (
        f"{_COMMENT_ONLY_KEY} .env.example'da yorum-ornegi olsa da "
        "docs/deploy-runbook.md tablosunda satiri olmali"
    )


def test_platform_etiketleri_ve_zorunlu_notlar_var():
    runbook = _runbook_text()
    for etiket in ("Fly secret", "Vercel env", "yalnız-local", "CI secret"):
        assert etiket in runbook, f"platform sinif etiketi eksik: {etiket!r}"

    for kritik in (
        "FLY_API_TOKEN",
        "GITHUB_APP_PRIVATE_KEY",
        "PEM",
        "VITE_API_BASE_URL",
        "alembic upgrade head",
        "Instant Rollback",
    ):
        assert kritik in runbook, f"kritik dizgi eksik: {kritik!r}"


def test_runbookta_sir_degeri_yok():
    runbook = _runbook_text()

    # Bilinen sir imzalari — hicbiri gercek bir ornekte/placeholder'da gorunmemeli.
    yasakli_desenler = (
        "-----BEGIN",
        "ghp_",
        "gho_",
        "AIza",
        "fo1_",  # Fly API token onexi
    )
    for desen in yasakli_desenler:
        assert desen not in runbook, f"runbook'ta sir-benzeri desen bulundu: {desen!r}"

    # `_KEY=` / `_SECRET=` / `_TOKEN=` sagindaki deger 20+ karakter ham metinse
    # (placeholder/bos DEGILSE) bu gercek bir sizinti olabilir. Placeholder'lar
    # `<...>` ya da bos oldugu icin bu desenle eslesmez.
    cig_deger_re = re.compile(r"[A-Z_]*(?:KEY|SECRET|TOKEN)=([^\s<`\"']{20,})")
    for eslesme in cig_deger_re.finditer(runbook):
        deger = eslesme.group(1)
        assert False, f"placeholder olmayan uzun deger bulundu: {deger!r}"


def test_smoke_hedefi_dogrulukla_ayirt_edilir():
    # #189 (`make smoke`) bu PR yazildiginda henuz `main`'de degil (Makefile'da
    # `smoke:` hedefi yok). Runbook, komutu "hedef durum" olarak acikca
    # etiketlemeli — main'e #190'dan ONCE inen bir kontrol bunu "bugun calisiyor"
    # gibi sunarsa yanlis olur (bilinçli/kosullu test — #56 ve #189
    # review'larindaki fail-open ders alinarak sabit degil, DURUMA gore yazildi).
    makefile = (_REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    runbook = _runbook_text()

    smoke_target_var = bool(re.search(r"^smoke:", makefile, re.MULTILINE))
    if smoke_target_var:
        # #189 main'e inmis -> runbook `make smoke`'u DOGRUDAN calisir komut
        # olarak belgeleyebilir; en azindan komutu icermeli.
        assert "make smoke" in runbook
    else:
        # #189 henuz main'de degil -> runbook bunu acikca "henuz main'de
        # degil" diye isaretlemis olmali (yanlis-canlilik vermesin, D-34 ruhu).
        assert "make smoke" in runbook, "runbook hedef durumu bile belgelemiyor"
        assert "henüz" in runbook and "main" in runbook, (
            "smoke hedefi main'de yokken runbook bunu acikca 'henuz main'de "
            "degil' diye isaretlemeli"
        )
