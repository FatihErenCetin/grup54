"""`.harness/` front-matter → JSON-schema doğrulayıcı (#55).

CI köprüsü: `.github/workflows/harness-validate.yml` her PR'da bunu çalıştırır
ki `.harness/` içindeki YAML front-matter'lar `src/shared/ensemble_shared/
schemas/*.json` sözleşmesinden sessizce kaymasın (audit boşluğu — bağlantı
dokusu).

Kasıtlı olarak KENDİ YAML/schema ayrıştırıcısını yazmaz: `FileHarnessPort`
zaten ".harness/ yollarına doğrudan değil bu modülün read_*/write_*'ı
üzerinden erişilir" ilkesinin TEK okuyucu/yazıcısıdır (dizin_yapisi §5).
Bu script de aynı `_read_markdown` yolunu (parse + schema-validate) kullanır
→ validator ile production ASLA farklı front-matter yorumlamaz.

Kullanım:
    uv run python scripts/harness_validate.py [repo-kök, varsayılan: .]

Çıkış kodu:
    0 → tüm dosyalar geçerli (ya da `.harness/` henüz yok — onboarding öncesi,
        kırmızı sayılmaz; dizin_yapisi.md'de "🟡 henüz yok" olarak işaretli).
    1 → en az bir dosyanın front-matter'ı ilgili şemayla uyuşmuyor.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SHARED_SRC = _REPO_ROOT / "src" / "shared"
if str(_SHARED_SRC) not in sys.path:
    sys.path.insert(0, str(_SHARED_SRC))

from ensemble_shared.harness import FileHarnessPort, HarnessError  # noqa: E402

# .harness/<klasör>/ adı -> front-matter "type" alanı (schemas/<type>.schema.json)
DIR_TO_TYPE = {
    "scope": "scope",
    "tasks": "task",
    "active": "active",
    "locks": "lock",
    "decisions": "decision",
}


def validate_harness(root: Path) -> list[str]:
    """`.harness/` altındaki her `*.md`'yi ilgili JSON-schema'ya göre doğrular.

    Döner: hata mesajı listesi (boşsa hepsi geçerli). `.harness/` hiç yoksa
    boş liste döner (henüz kurulmamış repo → doğrulanacak bir şey yok).
    """
    harness_dir = root / ".harness"
    if not harness_dir.exists():
        return []

    port = FileHarnessPort(root)
    errors: list[str] = []
    for dirname, doc_type in DIR_TO_TYPE.items():
        subdir = harness_dir / dirname
        if not subdir.exists():
            continue
        for path in sorted(subdir.glob("*.md")):
            try:
                # _read_markdown = üretimdeki TEK parse+validate yolu (bkz. modül docstring).
                port._read_markdown(path, doc_type)
            except HarnessError as exc:
                # .as_posix() → hata mesajı cross-platform '/' kullansın
                # (Windows '\' üretmesin; testler ve okunabilirlik için).
                errors.append(f"{path.relative_to(root).as_posix()}: {exc}")
    return errors


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    root = Path(args[0]).resolve() if args else _REPO_ROOT

    errors = validate_harness(root)
    if errors:
        print(f"HARNESS FRONT-MATTER DOĞRULAMA HATASI ({len(errors)}):")
        for err in errors:
            print(f"  - {err}")
        return 1

    print(".harness/ front-matter doğrulandı (JSON-schema uyumlu).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
