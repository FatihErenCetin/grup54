"""`.harness/` GERÇEKTEN git'e alınmış mı? (#242)

Ölçülen boşluk: `.harness/` repoda HİÇ yoktu (git'te 0 dosya, diskte de yok) —
ama `test_harness.py`/`test_harness_validate.py`'deki testlerin TAMAMI kendi
`tmp_path` fixture'ını `FileHarnessPort(tmp_path)` ile enjekte ediyordu; hiçbiri
gerçek repo köküne bakmıyordu. Sonuç: gerçek `.harness/` silinse/hiç
eklenmese bile mevcut test suite'i yeşil kalırdı (`scripts/harness_validate.py`
da `.harness/` yoksa no-op → CI de yeşildi). Bu dosya, gerçek repo köküne
karşı (fixture/temp-root DEĞİL) çalışarak o boşluğu kapatır: `.harness/`
eksikse ya da şemayla uyuşmuyorsa CI KIRMIZI olur.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from ensemble_shared.harness import FileHarnessPort
from scripts.harness_validate import validate_harness

# tests/unit/test_harness_git.py -> parents[2] = repo kökü (bkz. test_config.py'deki aynı desen).
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _git_tracked_harness_files() -> list[str]:
    """`.harness/` altında GERÇEKTEN commit'lenmiş (git-tracked) dosyaları döner.

    `git ls-files` kullanır — diskte var ama .gitignore'da/untracked kalan bir
    `.harness/` de aynı şekilde yakalanır (asıl ölçülen boşluk buydu: diskte
    onboarding sihirbazının bıraktığı dosyalar olabilir ama git'te 0 dosya).
    """
    result = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "ls-files", "--", ".harness"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def test_harness_dir_exists_on_disk():
    """`.harness/` gerçek repo kökünde bir dizin olarak var olmalı."""
    assert (_REPO_ROOT / ".harness").is_dir(), (
        ".harness/ repo kökünde yok — onboarding/backfill hiç çalışmamış ya da silinmiş."
    )


def test_harness_is_tracked_in_git_not_just_on_disk():
    """Asıl ölçülen boşluk: diskte olması yetmez, GIT'TE de olmalı (#242).

    `.gitignore`'a `.harness/` eklenip dosyalar yerelde bırakılırsa bu test
    kırmızı verir (tracked-file sayısı 0 kalır) — tam da bugünkü hatanın
    sessizce geri gelme yolu.
    """
    tracked = _git_tracked_harness_files()
    assert tracked, ".harness/ diskte olsa bile git'e hiç eklenmemiş (git ls-files boş döndü)."
    assert any(name.endswith("scope/sprint-3.md") for name in tracked)
    assert any(name.startswith(".harness/tasks/") for name in tracked)


def test_read_scope_sprint_3_does_not_raise_against_real_repo_root():
    """Ölçülen başlangıç durumu: `read_scope('sprint-3')` HarnessError fırlatıyordu."""
    port = FileHarnessPort(_REPO_ROOT)
    scope = port.read_scope("sprint-3")
    assert scope["type"] == "scope"
    assert scope["sprint"] == "3"
    assert scope["title"]


def test_read_tasks_is_not_empty_against_real_repo_root():
    """Ölçülen başlangıç durumu: `read_tasks()` boş liste dönüyordu."""
    port = FileHarnessPort(_REPO_ROOT)
    tasks = port.read_tasks()
    assert tasks, "tasks/ altında hiç dosya okunamadı — .harness/tasks/ boş ya da eksik."
    assert all(task["type"] == "task" for task in tasks)


def test_real_harness_front_matter_validates_clean():
    """`scripts/harness_validate.py` (CI'ın koştuğu AYNI fonksiyon) gerçek
    repo köküne karşı sıfır hata dönmeli — front-matter/şema drift'i burada
    yakalanır (bkz. `.github/workflows/harness-validate.yml`)."""
    errors = validate_harness(_REPO_ROOT)
    assert errors == []
