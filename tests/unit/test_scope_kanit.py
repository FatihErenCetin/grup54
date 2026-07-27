"""#257 bulgu 1-2 — scope front-matter'ının kanıt bağlantısı ÇÖZÜLEBİLİR olmalı.

Sözleşme (`docs/sprint2-kontratlar.md:229`) `commit_sha`'yı *"donmuş dosyanın
SHA'sı — `#L14` evidence linki"* diye tanımlıyor. Amaç şu biçimde bir permalink:

    https://github.com/<repo>/blob/<commit_sha>/.harness/scope/sprint-3.md#L14

Bulunan durum (2026-07-26 inceleme, 2026-07-27 doğrulandı): `ref: main` (bir
DAL adı, yol değil) ve `commit_sha: 5cf2009...` — o commit'te bu dosya HİÇ
YOKTU. Yani ikisinden çalışan bir permalink kurulamıyordu.

İnceleme sırasında ciddiyet "küçük"e düşürülmüştü çünkü o gün TÜKETİCİ yoktu
(`ScopePage.tsx` 11 satırlık bir placeholder'dı). Bugün ScopePage 453 satır ve
`ref`'i kullanıcıya BASIYOR (`<Kunye etiket="ref" deger={scope.ref} />`) —
yani jüri Scope sayfasında "kanıt bağlantısı: main" yazısını görüyordu.
"Bugün tüketicisi yok" bir düzeltmeyi erteleme gerekçesiyse, tüketici geldiğinde
kimse geri dönüp bakmıyor: bu testler o dönüşü zorunlu kılıyor.
"""

import re
import subprocess
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parents[2]
_SCOPE_DIZIN = _KOK / ".harness" / "scope"


def _front_matter(yol: Path) -> dict[str, str]:
    """Basit YAML front-matter okuyucu — yalnız düz `anahtar: değer` satırları.

    Bilerek tam bir YAML parser değil: bu test şemayı değil, İKİ ALANIN
    tutarlılığını ölçüyor. Tam parse `harness_validate.py`'nin işi.
    """
    metin = yol.read_text(encoding="utf-8")
    if not metin.startswith("---"):
        return {}
    govde = metin.split("---", 2)[1]
    alanlar: dict[str, str] = {}
    for satir in govde.splitlines():
        eslesme = re.match(r"^([a-z_]+):\s*(.+?)\s*$", satir)
        if eslesme:
            alanlar[eslesme.group(1)] = eslesme.group(2).strip().strip("'\"")
    return alanlar


def _scope_dosyalari() -> list[Path]:
    return sorted(_SCOPE_DIZIN.glob("sprint-*.md"))


def _sig_klon_mu() -> bool:
    sonuc = subprocess.run(
        ["git", "rev-parse", "--is-shallow-repository"],
        cwd=_KOK, capture_output=True, text=True,
    )
    return sonuc.stdout.strip() == "true"


def test_scope_dosyasi_var():
    """Bu testlerin geri kalanı boş bir dizinde SESSİZCE geçmesin.

    `glob` boş dönerse aşağıdaki parametrik testler hiç koşmaz ve takım
    "scope kilitleri yeşil" sanır — kilit yokken. (Bu repoda defalarca
    yakalanan desen: sayı/varlık iddia etmeyen test, hiçbir şeyi tutmaz.)
    """
    dosyalar = _scope_dosyalari()
    assert dosyalar, f"{_SCOPE_DIZIN} altında sprint-*.md yok — kilitler koşmuyor demektir"


@pytest.mark.parametrize("yol", _scope_dosyalari(), ids=lambda p: p.name)
def test_ref_dosyanin_KENDI_YOLU(yol: Path):
    """`ref` bir DAL adı değil, dosyanın repo-göreli yolu olmalı.

    Motorun kendi fallback'i bunu söylüyor (`engine/scope.py:120`):
        "ref": scope.get("ref") or scope.get("path")
    Fallback bir DOSYA YOLU üretir — dal adı bekleniyor olsaydı yola düşmek
    anlamsız olurdu. `tests/unit/test_scope.py:295` de yol semantiğini
    kilitliyor, ama fake veriyle çalıştığı için GERÇEK dosyadaki sapmayı
    göremiyordu. Bu test gerçek dosyaya bakar.
    """
    alanlar = _front_matter(yol)
    ref = alanlar.get("ref")
    if ref is None:
        pytest.skip("ref alanı yok — motor fallback ile yolu üretir (geçerli)")
    beklenen = yol.relative_to(_KOK).as_posix()
    assert ref == beklenen, (
        f"ref='{ref}' ama dosyanın yolu '{beklenen}'. "
        "'main' gibi bir dal adı yazılırsa kanıt bağlantısı çözülmez."
    )


@pytest.mark.parametrize("yol", _scope_dosyalari(), ids=lambda p: p.name)
def test_commit_sha_dosyanin_VAR_OLDUGU_bir_commiti_gosterir(yol: Path):
    """Asıl kilit: `blob/<commit_sha>/<yol>` permalink'i ÇÖZÜLEBİLMELİ.

    MUTASYON KİLİDİ: `commit_sha`'yı dosyanın henüz eklenmediği bir commit'e
    (örn. kaynak belgenin commit'i) çevir → kırmızı.
    """
    alanlar = _front_matter(yol)
    sha = alanlar.get("commit_sha")
    if sha is None:
        pytest.skip("commit_sha alanı yok")

    assert re.fullmatch(r"[0-9a-f]{40}", sha), f"commit_sha 40 haneli hex olmalı: {sha!r}"

    if _sig_klon_mu():
        pytest.skip(
            "sığ klon (shallow) — geçmiş yok, doğrulanamaz. "
            "CI'da `fetch-depth: 0` ile bu atlanmamalı."
        )

    goreli = yol.relative_to(_KOK).as_posix()
    sonuc = subprocess.run(
        ["git", "cat-file", "-e", f"{sha}:{goreli}"],
        cwd=_KOK, capture_output=True, text=True,
    )
    assert sonuc.returncode == 0, (
        f"'{goreli}' dosyası {sha[:12]} commit'inde YOK — "
        f"blob/{sha[:12]}/{goreli}#L14 kanıt bağlantısı çözülmez. "
        "Kapsam yeniden dondurulduysa commit_sha yeniden pinlenmeli."
    )


@pytest.mark.parametrize("yol", _scope_dosyalari(), ids=lambda p: p.name)
def test_frozen_scope_status_gecerli(yol: Path):
    """`ScopeService` yalnız `frozen` durumunu kullanılabilir sayar
    (`engine/scope.py::get_current_scope`); başka değerde `/scope/current`
    503 döner. Sessizce `draft`a düşmüş bir dosya, canlıda kapsam
    kontrolünü tamamen kapatır."""
    durum = _front_matter(yol).get("status")
    assert durum == "frozen", (
        f"status='{durum}' — `frozen` değilse GET /scope/current 503 döner "
        "ve scope-drift kontrolü sessizce kapanır"
    )
