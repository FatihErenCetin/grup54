import json
from importlib import resources
from pathlib import Path
from textwrap import dedent

import pytest
from jsonschema import Draft202012Validator

from ensemble_shared.harness import FileHarnessPort, HarnessError, HarnessValidationError


def write_md(path: Path, frontmatter: str, body: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{dedent(frontmatter).strip()}\n---\n{body}", encoding="utf-8")


def test_read_scope_validates_frontmatter(tmp_path: Path):
    write_md(
        tmp_path / ".harness/scope/sprint-2.md",
        """
        type: scope
        sprint: "2"
        title: Sprint 2 scope
        """,
        "Only harness IO is in scope.\n",
    )

    scope = FileHarnessPort(tmp_path).read_scope("2")
    assert scope["title"] == "Sprint 2 scope"
    assert scope["body"] == "Only harness IO is in scope."
    assert scope["path"] == ".harness/scope/sprint-2.md"


def test_read_tasks_validates_task_frontmatter(tmp_path: Path):
    write_md(
        tmp_path / ".harness/tasks/T-13.md",
        """
        type: task
        task_id: T-13
        title: Harness port
        status: in_progress
        assignee: asmarufoglu
        paths:
          - src/shared/ensemble_shared/harness.py
        """,
    )

    tasks = FileHarnessPort(tmp_path).read_tasks()
    assert len(tasks) == 1
    assert tasks[0]["task_id"] == "T-13"
    assert tasks[0]["paths"] == ["src/shared/ensemble_shared/harness.py"]


def test_read_active_validates_active_frontmatter(tmp_path: Path):
    write_md(
        tmp_path / ".harness/active/asmarufoglu.md",
        """
        type: active
        handle: asmarufoglu
        task_id: T-13
        branch: T-13-harness-port
        paths:
          - src/shared/ensemble_shared/harness.py
        updated_at: "2026-07-03T12:00:00+03:00"
        """,
    )

    active = FileHarnessPort(tmp_path).read_active()
    assert len(active) == 1
    assert active[0]["handle"] == "asmarufoglu"
    assert active[0]["task_id"] == "T-13"


def test_invalid_frontmatter_raises_validation_error(tmp_path: Path):
    write_md(
        tmp_path / ".harness/active/asmarufoglu.md",
        """
        type: active
        handle: asmarufoglu
        branch: T-13-harness-port
        paths: []
        updated_at: "2026-07-03T12:00:00+03:00"
        """,
    )

    with pytest.raises(HarnessValidationError, match="task_id"):
        FileHarnessPort(tmp_path).read_active()


def test_write_active_creates_one_atomic_file_per_handle(tmp_path: Path):
    port = FileHarnessPort(tmp_path)

    port.write_active(
        "asmarufoglu",
        {
            "task_id": "T-13",
            "branch": "T-13-harness-port",
            "paths": ["src/shared/ensemble_shared/harness.py"],
            "updated_at": "2026-07-03T12:00:00+03:00",
            "body": "Working on HarnessPort.",
        },
    )
    port.write_active(
        "asmarufoglu",
        {
            "task_id": "T-13",
            "branch": "T-13-harness-port-v2",
            "paths": [
                "src/shared/ensemble_shared/harness.py",
                "src/shared/ensemble_shared/schemas/active.schema.json",
            ],
            "updated_at": "2026-07-03T12:05:00+03:00",
        },
    )

    active_files = sorted((tmp_path / ".harness/active").glob("*.md"))
    assert active_files == [tmp_path / ".harness/active/asmarufoglu.md"]

    active = port.read_active()[0]
    assert active["branch"] == "T-13-harness-port-v2"
    assert active["handle"] == "asmarufoglu"


def test_rejects_unsafe_active_handle(tmp_path: Path):
    with pytest.raises(HarnessValidationError, match="Unsafe active handle"):
        FileHarnessPort(tmp_path).write_active("../enes", {})


def test_read_scope_missing_file_raises_harness_error(tmp_path: Path):
    with pytest.raises(HarnessError, match="Harness file not found"):
        FileHarnessPort(tmp_path).read_scope("2")


def test_write_task_creates_slugged_file_and_round_trips(tmp_path: Path):
    port = FileHarnessPort(tmp_path)

    port.write_task(
        "T-57",
        {"title": "Onboarding: greenfield + brownfield!", "status": "backlog", "paths": []},
    )

    files = sorted((tmp_path / ".harness/tasks").glob("*.md"))
    assert files == [tmp_path / ".harness/tasks/T-57-onboarding-greenfield-brownfield.md"]

    task = port.read_tasks()[0]
    assert task["task_id"] == "T-57"
    assert task["status"] == "backlog"


def test_write_task_slug_strips_unsafe_characters(tmp_path: Path):
    """Path traversal denemesi bile slug'a indirgenip zararsızlaşır."""
    port = FileHarnessPort(tmp_path)

    port.write_task("T-1", {"title": "../../etc/passwd", "status": "backlog"})

    files = list((tmp_path / ".harness/tasks").glob("*.md"))
    assert len(files) == 1
    assert ".." not in files[0].name
    assert files[0].parent == tmp_path / ".harness/tasks"


def test_write_scope_round_trips(tmp_path: Path):
    port = FileHarnessPort(tmp_path)

    port.write_scope(
        "3",
        {"title": "Sprint 3", "status": "draft", "goals": ["a"], "non_goals": ["b"]},
    )

    scope = port.read_scope("3")
    assert scope["title"] == "Sprint 3"
    assert scope["sprint"] == "3"
    assert scope["status"] == "draft"
    assert scope["path"] == ".harness/scope/sprint-3.md"


def test_write_scope_rejects_unsafe_sprint_id(tmp_path: Path):
    with pytest.raises(HarnessValidationError, match="Unsafe sprint id"):
        FileHarnessPort(tmp_path).write_scope("../evil", {"title": "x"})


# --- #83 sertleştirme testleri ---


def test_read_scope_rejects_unsafe_sprint(tmp_path: Path):
    with pytest.raises(HarnessValidationError, match="Unsafe sprint id"):
        FileHarnessPort(tmp_path).read_scope("../../etc/passwd")


def test_frontmatter_block_scalar_with_dashes_is_parsed(tmp_path: Path):
    write_md(
        tmp_path / ".harness/active/fatih.md",
        """
        type: active
        handle: fatih
        task_id: T-83
        branch: T-83-harness-io-sertlestirme
        paths: []
        updated_at: "2026-07-05T12:00:00+03:00"
        intent: |
          plan:
          ---
          devam ediyor
        """,
    )

    active = FileHarnessPort(tmp_path).read_active()
    assert "---" in active[0]["intent"]


def test_unquoted_iso_datetime_is_coerced_to_string(tmp_path: Path):
    write_md(
        tmp_path / ".harness/active/fatih.md",
        """
        type: active
        handle: fatih
        task_id: T-83
        branch: T-83-harness-io-sertlestirme
        paths: []
        updated_at: 2026-07-05T12:00:00
        """,
    )

    active = FileHarnessPort(tmp_path).read_active()
    assert active[0]["updated_at"] == "2026-07-05T12:00:00"


def test_utf8_bom_file_is_accepted(tmp_path: Path):
    path = tmp_path / ".harness/tasks/T-1.md"
    path.parent.mkdir(parents=True)
    content = "---\ntype: task\ntask_id: T-1\ntitle: x\nstatus: todo\n---\n"
    path.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))

    assert FileHarnessPort(tmp_path).read_tasks()[0]["task_id"] == "T-1"


def test_all_packaged_schemas_are_valid_jsonschema():
    schemas = resources.files("ensemble_shared").joinpath("schemas")
    names = sorted(p.name for p in schemas.iterdir() if p.name.endswith(".schema.json"))
    assert names == [
        "active.schema.json",
        "decision.schema.json",
        "lock.schema.json",
        "scope.schema.json",
        "task.schema.json",
    ]
    for name in names:
        Draft202012Validator.check_schema(json.loads(schemas.joinpath(name).read_text(encoding="utf-8")))
