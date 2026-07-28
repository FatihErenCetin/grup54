import json
import logging
from pathlib import Path

from ensemble.integrations.github.normalize import (
    commit_to_event,
    extract_task_id,
    issue_to_event,
    pr_to_event,
    webhook_push_to_events,
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
    # commit_detail.json'da author.login="esma" var -> GERÇEK GitHub hesabı
    # eşleşti, doğrulanmış (#296).
    assert event.actor_verified is True


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


# --- Aktör doğrulama (#296, T-296) — gerçek GitHub REST commits payload
# şekilleri: `author: null` (e-posta bir hesapla eşleşmedi) vs
# `author: {login: "..."}` (eşleşti). ---


def test_commit_to_event_author_null_ise_ham_ada_duser_ve_isaretlenir(caplog):
    """GERÇEK GitHub şekli: yazarın e-postası hiçbir hesapla eşleşmediğinde
    REST commits API'si `author: null` döner (`commit.author.name` HER ZAMAN
    vardır - ham git config adı). #296'nın "Merge Simulation" vakası budur."""
    commit = {
        "sha": "d35e739",
        "author": None,
        "commit": {"author": {"name": "Merge Simulation", "date": "2026-07-20T09:00:00Z"}},
        "files": [],
    }
    with caplog.at_level(logging.WARNING, logger="ensemble.normalize"):
        event = commit_to_event(commit)

    assert event.actor == "Merge Simulation"
    assert event.actor_verified is False
    # Log, operatörün "neden sahte aktör var" sorusunu kod okumadan
    # cevaplamasını sağlar (hangi commit, hangi ham ad).
    assert any("d35e739" in r.message and "Merge Simulation" in r.message for r in caplog.records)


def test_commit_to_event_login_varsa_ham_ad_kullanilmaz(caplog):
    """Tercih sırası KİLİDİ: `author.login` VARSA `commit.author.name`
    (farklı bir ad taşısa bile) ASLA kullanılmaz - MUTASYON KİLİDİ #1
    (bkz. PR gövdesi: tercih sırası ters çevrilince bu test kırmızı olur)."""
    commit = {
        "sha": "aaa2222",
        "author": {"login": "esma6"},
        "commit": {"author": {"name": "Esma Fazilet Karagülle", "date": "2026-07-20T09:00:00Z"}},
        "files": [],
    }
    with caplog.at_level(logging.WARNING, logger="ensemble.normalize"):
        event = commit_to_event(commit)

    assert event.actor == "esma6"
    assert event.actor_verified is True
    assert not any(r.levelno >= logging.WARNING for r in caplog.records)


def test_commit_to_event_login_bos_string_de_eslesmemis_sayilir():
    """Savunmacı: `author.login` boş string ise (gerçek GitHub'da beklenmez
    ama savunmacı kod bunu da "yok" saymalı) ham ada düşülür - `or None`
    normalizasyonu falsy'yi de kapsar."""
    commit = {
        "sha": "bbb3333",
        "author": {"login": ""},
        "commit": {"author": {"name": "ham-ad", "date": "2026-07-20T09:00:00Z"}},
        "files": [],
    }
    event = commit_to_event(commit)
    assert event.actor == "ham-ad"
    assert event.actor_verified is False


# --- webhook `push` şekli (author.username eşleşme sinyali; REST'ten FARKLI
# alan adı) ---


def test_webhook_push_username_yoksa_ham_ada_duser_ve_isaretlenir(caplog):
    """GERÇEK webhook şekli: `author.username` yalnızca e-posta bir GitHub
    hesabıyla eşleştiğinde vardır; eşleşmediğinde alan hiç YOKTUR (yalnız
    `name`/`email` gelir)."""
    payload = {
        "ref": "refs/heads/T-urun-goruntuleri",
        "commits": [
            {
                "id": "d35e739",
                "timestamp": "2026-07-20T10:00:00+03:00",
                "author": {"name": "Merge Simulation", "email": "verify-sim@local"},
                "added": [],
                "removed": [],
                "modified": ["README.md"],
            }
        ],
    }
    with caplog.at_level(logging.WARNING, logger="ensemble.normalize"):
        events = webhook_push_to_events(payload)

    assert len(events) == 1
    assert events[0].actor == "Merge Simulation"
    assert events[0].actor_verified is False
    assert any("d35e739" in r.message and "Merge Simulation" in r.message for r in caplog.records)


def test_webhook_push_username_varsa_ham_ad_kullanilmaz(caplog):
    """Tercih sırası KİLİDİ (webhook tarafı): `author.username` VARSA
    `author.name` ASLA kullanılmaz - MUTASYON KİLİDİ #2."""
    payload = {
        "ref": "refs/heads/T-99-x",
        "commits": [
            {
                "id": "abc999",
                "timestamp": "2026-07-20T10:00:00+03:00",
                "author": {"username": "esma6", "name": "Esma Fazilet Karagülle"},
                "added": ["x.py"],
                "removed": [],
                "modified": [],
            }
        ],
    }
    with caplog.at_level(logging.WARNING, logger="ensemble.normalize"):
        events = webhook_push_to_events(payload)

    assert events[0].actor == "esma6"
    assert events[0].actor_verified is True
    assert not any(r.levelno >= logging.WARNING for r in caplog.records)
