"""`.harness/` front-matter → JSON-schema doğrulayıcı testleri (#55).

Kabul kriteri odağı: gerçek şekildeki `.harness/*` dosyaları temiz geçmeli,
kasten bozuk front-matter kırmızı vermeli, `.harness/` hiç yoksa (onboarding
öncesi) no-op geçmeli.
"""

from pathlib import Path
from textwrap import dedent

from scripts.harness_validate import main, validate_harness


def write_md(path: Path, frontmatter: str, body: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{dedent(frontmatter).strip()}\n---\n{body}", encoding="utf-8")


def test_missing_harness_dir_is_not_an_error(tmp_path: Path):
    """Onboarding öncesi `.harness/` hiç yoksa doğrulanacak bir şey yok — kırmızı değil."""
    assert validate_harness(tmp_path) == []
    assert main([str(tmp_path)]) == 0


def test_valid_files_across_all_five_types_pass(tmp_path: Path):
    write_md(
        tmp_path / ".harness/scope/sprint-3.md",
        """
        type: scope
        sprint: "3"
        title: Sprint 3 scope
        """,
    )
    write_md(
        tmp_path / ".harness/tasks/T-55.md",
        """
        type: task
        task_id: T-55
        title: Harness validate CI
        status: in_progress
        """,
    )
    write_md(
        tmp_path / ".harness/active/fatih.md",
        """
        type: active
        handle: fatih
        task_id: T-55
        branch: T-55-harness-validate-ci
        paths: []
        updated_at: "2026-07-21T12:00:00+03:00"
        """,
    )
    write_md(
        tmp_path / ".harness/locks/L-1.md",
        """
        type: lock
        id: L-1
        owner: fatih
        paths: [scripts/harness_validate.py]
        """,
    )
    write_md(
        tmp_path / ".harness/decisions/D-27.md",
        """
        type: decision
        id: D-27
        title: harness-validate CI eklendi
        date: "2026-07-21"
        """,
    )

    assert validate_harness(tmp_path) == []
    assert main([str(tmp_path)]) == 0


def test_broken_frontmatter_fails_red(tmp_path: Path):
    """Şemayla uyuşmayan front-matter (task_id eksik) kırmızı vermeli."""
    write_md(
        tmp_path / ".harness/active/fatih.md",
        """
        type: active
        handle: fatih
        branch: T-55-harness-validate-ci
        paths: []
        updated_at: "2026-07-21T12:00:00+03:00"
        """,
    )

    errors = validate_harness(tmp_path)
    assert len(errors) == 1
    assert "active/fatih.md" in errors[0]
    assert "task_id" in errors[0]
    assert main([str(tmp_path)]) == 1


def test_missing_frontmatter_delimiter_fails_red(tmp_path: Path):
    path = tmp_path / ".harness/tasks/T-99.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("Bu dosyanın front-matter'ı yok.\n", encoding="utf-8")

    errors = validate_harness(tmp_path)
    assert len(errors) == 1
    assert main([str(tmp_path)]) == 1
