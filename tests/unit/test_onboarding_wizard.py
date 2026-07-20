"""Onboarding sihirbazı (#57) testleri.

Fixture issue listesiyle brownfield, boş listeyle greenfield, "zaten var"
güvenlik atlaması. Gerçek `gh`/Gemini çağrısı YOK (FakeScopeDrafter +
enjekte edilen issue listesi).
"""

from pathlib import Path

import pytest

from ensemble.config import Settings
from ensemble.onboarding.scope_draft import FakeScopeDrafter, ScopeDraft
from ensemble.onboarding.wizard import _sprint_slug, init_harness
from ensemble_shared.harness import FileHarnessPort

_FIXTURE_ISSUES = [
    {"number": 30, "title": "make eval + CI precision-gate", "assignees": [{"login": "FatihErenCetin"}]},
    {"number": 124, "title": "Bağımlılık haritası botu", "assignees": []},
]


def _settings() -> Settings:
    return Settings(_env_file=None)


def test_zaten_varsa_dokunmaz(tmp_path: Path):
    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "sentinel.txt").write_text("dokunma")

    result = init_harness(tmp_path, milestone="Sprint 3", settings=_settings(), issues=[])

    assert result.mode == "skipped"
    assert (tmp_path / ".harness" / "sentinel.txt").exists()


def test_brownfield_taska_donusturur(tmp_path: Path):
    result = init_harness(
        tmp_path,
        milestone="Sprint 3",
        settings=_settings(),
        issues=_FIXTURE_ISSUES,
        scope_drafter=FakeScopeDrafter(),
    )

    assert result.mode == "brownfield"
    port = FileHarnessPort(tmp_path)
    tasks = {t["task_id"]: t for t in port.read_tasks()}
    assert set(tasks) == {"T-30", "T-124"}
    assert tasks["T-30"]["assignee"] == "FatihErenCetin"
    assert tasks["T-124"]["assignee"] is None
    assert all(t["status"] == "backlog" for t in tasks.values())


def test_brownfield_scope_taslak_olarak_yazilir(tmp_path: Path):
    init_harness(
        tmp_path,
        milestone="Sprint 3",
        settings=_settings(),
        issues=_FIXTURE_ISSUES,
        scope_drafter=FakeScopeDrafter(),
    )

    scope = FileHarnessPort(tmp_path).read_scope("3")
    assert scope["status"] == "draft"
    assert scope["title"] == "Sprint 3"
    assert "TASLAK" in scope["body"]


def test_scope_drafter_cagrilirken_context_iceriyor(tmp_path: Path, monkeypatch):
    """Gerçek AI adımı: drafter'a issue başlıklarını içeren bir context geçiyor mu?"""
    captured = {}

    class _CapturingDrafter:
        def draft(self, *, milestone, context):
            captured["milestone"] = milestone
            captured["context"] = context
            return ScopeDraft(goal="g", in_scope=["a"], non_goals=["b"])

    init_harness(
        tmp_path,
        milestone="Sprint 3",
        settings=_settings(),
        issues=_FIXTURE_ISSUES,
        scope_drafter=_CapturingDrafter(),
    )

    assert captured["milestone"] == "Sprint 3"
    assert "#30" in captured["context"]
    assert "#124" in captured["context"]


def test_greenfield_ai_cagirmaz_sablon_yazar(tmp_path: Path):
    class _ExplodingDrafter:
        def draft(self, *, milestone, context):
            raise AssertionError("greenfield'da AI çağrılmamalı")

    result = init_harness(
        tmp_path,
        milestone="Sprint 1",
        settings=_settings(),
        issues=[],
        scope_drafter=_ExplodingDrafter(),
    )

    assert result.mode == "greenfield"
    port = FileHarnessPort(tmp_path)
    assert len(port.read_tasks()) == 1
    assert port.read_scope("1")["status"] == "draft"


def test_drafter_patlarsa_harness_yarim_kalmaz(tmp_path: Path):
    """#57 review (Fatih + Semih, bağımsız aynı repro): drafter hata verirse
    .harness/ hiç oluşmamalı - aksi halde ikinci çalıştırma "zaten var" sanıp
    atlar ve operatör kurulumun bittiğini zanneder."""
    class _ExplodingDrafter:
        def draft(self, *, milestone, context):
            raise RuntimeError("gemini-timeout")

    with pytest.raises(RuntimeError, match="gemini-timeout"):
        init_harness(
            tmp_path,
            milestone="Sprint 3",
            settings=_settings(),
            issues=_FIXTURE_ISSUES,
            scope_drafter=_ExplodingDrafter(),
        )

    assert not (tmp_path / ".harness").exists()

    # Retry temiz calismali - "zaten var" diye atlamamali.
    result = init_harness(
        tmp_path,
        milestone="Sprint 3",
        settings=_settings(),
        issues=_FIXTURE_ISSUES,
        scope_drafter=FakeScopeDrafter(),
    )
    assert result.mode == "brownfield"


def test_bos_kategoriler_ve_readme_her_modda_yazilir(tmp_path: Path):
    init_harness(
        tmp_path, milestone="Sprint 1", settings=_settings(), issues=[],
    )

    for name in ("active", "locks", "decisions"):
        assert (tmp_path / ".harness" / name / ".gitkeep").exists()
    assert (tmp_path / ".harness" / "README.md").exists()


@pytest.mark.parametrize(
    ("milestone", "expected"),
    [("Sprint 3", "3"), ("Sprint 12", "12"), ("Kickoff", "kickoff")],
)
def test_sprint_slug(milestone, expected):
    assert _sprint_slug(milestone) == expected
