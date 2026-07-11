import json
from pathlib import Path

from ensemble.integrations.github.normalize import (
    commit_to_event,
    extract_task_id,
    issue_to_event,
    pr_to_event,
)

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "github_api"


def _load(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def test_extract_task_id_from_branch():
    assert extract_task_id(branch="T-16-github-ingest") == "16"


def test_extract_task_id_from_pr_body():
    assert extract_task_id(pr_body="Closes #42 - bir seyler") == "42"


def test_extract_task_id_branch_takes_priority_over_body():
    assert extract_task_id(branch="T-16-x", pr_body="Closes #99") == "16"


def test_extract_task_id_none_when_no_match():
    assert extract_task_id(branch="feature/random", pr_body="no ref here") is None


def test_commit_to_event():
    detail = _load("commit_detail.json")
    event = commit_to_event(detail)
    assert event.type == "commit"
    assert event.actor == "esma"
    assert event.ref == "aaa1111"
    assert "src/backend/ensemble/integrations/gemini/judge.py" in event.files


def test_pr_to_event():
    prs = _load("pulls_list.json")
    event = pr_to_event(prs[0])
    assert event.type == "pr"
    assert event.branch == "T-99-ornek-ozellik"
    assert event.files == []
    assert event.ref == "99"


def test_issue_to_event():
    issues = _load("issues_list.json")
    event = issue_to_event(issues[0])
    assert event.type == "issue"
    assert event.actor == "enes"
    assert event.ref == "50"
