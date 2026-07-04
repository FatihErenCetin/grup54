from datetime import datetime

import pytest
from pydantic import ValidationError

from ensemble.models import BoardCard, Detection, NormalizedEvent, ScopeVerdict


def test_normalized_event_valid():
    event = NormalizedEvent(
        id="123",
        type="commit",
        actor="fatih",
        branch="main",
        files=["src/main.py"],
        ts=datetime.now(),
        ref="abc1234",
    )
    assert event.type == "commit"
    assert "src/main.py" in event.files


def test_normalized_event_invalid_type():
    with pytest.raises(ValidationError):
        NormalizedEvent(
            id="123",
            type="invalid_type",  # type: ignore
            actor="fatih",
            branch="main",
            files=["src/main.py"],
            ts=datetime.now(),
            ref="abc1234",
        )


def test_detection_valid():
    detection = Detection(
        id="det-1",
        kind="conflict",
        actors=["fatih", "enes"],
        branches=["feat-a", "feat-b"],
        files=["app.py"],
        severity="high",
        confidence=0.95,
        rationale="Both modified same function",
    )
    assert detection.severity == "high"


def test_scope_verdict_valid():
    verdict = ScopeVerdict(
        ref="PR-1",
        verdict="drift",
        confidence=0.8,
        evidence="Modified undocumented API",
    )
    assert verdict.verdict == "drift"


def test_board_card_valid():
    card = BoardCard(
        task_id="T-1", title="Task 1", status="todo", assignee=None, ref=None
    )
    assert card.status == "todo"
