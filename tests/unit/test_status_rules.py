"""status_rules.py testleri — saf durum geçişi türetimi (İş 1).

Payload şekilleri test_webhook.py'deki inline dict stiliyle birebir aynı
(gerçek GitHub webhook gövdesi; `pull_request`/`issue` REST kaynağının
AYNISI — api/routers/webhook.py docstring'i).
"""

from datetime import datetime

from ensemble.engine.status_rules import (
    STATUS_RANK,
    StatusTransition,
    next_status,
    transitions_from_resources,
    transitions_from_webhook,
)
from ensemble.integrations.github.normalize import (
    issue_to_event,
    pr_to_event,
    webhook_push_to_events,
)

# --- ortak yardımcı ---


def _t(status: str, resets: bool = False) -> StatusTransition:
    """next_status testleri için gövdesi önemsiz bir StatusTransition üretir."""
    return StatusTransition(
        task_id="T-1",
        status=status,
        ts=datetime(2026, 7, 20, 10, 0, 0),
        source_event_id="issue:1:2026-07-20T10:00:00Z",
        reason="test",
        resets=resets,
    )


# --- issues ---


def test_issues_closed_uretir_done():
    payload = {
        "action": "closed",
        "issue": {"number": 158, "updated_at": "2026-07-25T09:00:00Z", "user": {"login": "esma"}},
    }
    transitions = transitions_from_webhook("issues", payload)
    assert len(transitions) == 1
    t = transitions[0]
    assert t.task_id == "T-158"
    assert t.status == "done"
    assert t.reason == "issue_closed"
    assert t.resets is False


def test_issues_reopened_uretir_todo_ve_resets_true():
    payload = {
        "action": "reopened",
        "issue": {"number": 158, "updated_at": "2026-07-25T09:00:00Z", "user": {"login": "esma"}},
    }
    transitions = transitions_from_webhook("issues", payload)
    assert len(transitions) == 1
    t = transitions[0]
    assert t.task_id == "T-158"
    assert t.status == "todo"
    assert t.reason == "issue_reopened"
    assert t.resets is True


def test_issues_diger_action_bos_liste():
    payload = {
        "action": "labeled",
        "issue": {"number": 158, "updated_at": "2026-07-25T09:00:00Z", "user": {"login": "esma"}},
    }
    assert transitions_from_webhook("issues", payload) == []


# --- pull_request: merge -> done ---


def test_pr_merged_done_uretir():
    payload = {
        "action": "closed",
        "pull_request": {
            "number": 258,
            "updated_at": "2026-07-25T11:00:00Z",
            "user": {"login": "fatih"},
            "head": {"ref": "T-158-fix-thing"},
            "body": "bir seyler duzeltir",
            "merged": True,
        },
    }
    transitions = transitions_from_webhook("pull_request", payload)
    assert len(transitions) == 1
    t = transitions[0]
    assert t.task_id == "T-158"
    assert t.status == "done"
    assert t.reason == "pr_merged"


def test_kapatan_pr_govdesindeki_tum_closes_islenir():
    """Branch T-158 VE gövdedeki iki ayrı `Closes #N` -> ÜÇ farklı task done olur."""
    payload = {
        "action": "closed",
        "pull_request": {
            "number": 258,
            "updated_at": "2026-07-25T11:00:00Z",
            "user": {"login": "fatih"},
            "head": {"ref": "T-158-fix-thing"},
            "body": "Closes #200 ve ayrica Closes #201 de kapatir",
            "merged": True,
        },
    }
    transitions = transitions_from_webhook("pull_request", payload)
    task_ids = {t.task_id for t in transitions}
    assert task_ids == {"T-158", "T-200", "T-201"}
    assert all(t.status == "done" for t in transitions)


def test_pr_govde_ve_branch_ayni_task_i_isaret_ederse_tekillestirilir():
    payload = {
        "action": "closed",
        "pull_request": {
            "number": 258,
            "updated_at": "2026-07-25T11:00:00Z",
            "user": {"login": "fatih"},
            "head": {"ref": "T-158-fix-thing"},
            "body": "Closes #158",
            "merged": True,
        },
    }
    transitions = transitions_from_webhook("pull_request", payload)
    assert len(transitions) == 1
    assert transitions[0].task_id == "T-158"


def test_pr_kapali_merge_edilmemis_gecis_uretilmez():
    payload = {
        "action": "closed",
        "pull_request": {
            "number": 258,
            "updated_at": "2026-07-25T11:00:00Z",
            "user": {"login": "fatih"},
            "head": {"ref": "T-158-fix-thing"},
            "body": "Closes #200",
            "merged": False,
        },
    }
    assert transitions_from_webhook("pull_request", payload) == []


# --- pull_request: opened/reopened/ready_for_review -> in_review ---


def test_pr_opened_uretir_in_review():
    payload = {
        "action": "opened",
        "pull_request": {
            "number": 42,
            "updated_at": "2026-07-20T10:00:00Z",
            "user": {"login": "esma6"},
            "head": {"ref": "T-99-ornek-dal"},
        },
    }
    transitions = transitions_from_webhook("pull_request", payload)
    assert len(transitions) == 1
    t = transitions[0]
    assert t.task_id == "T-99"
    assert t.status == "in_review"


def test_pr_ready_for_review_uretir_in_review():
    payload = {
        "action": "ready_for_review",
        "pull_request": {
            "number": 42,
            "updated_at": "2026-07-20T10:00:00Z",
            "user": {"login": "esma6"},
            "head": {"ref": "T-99-ornek-dal"},
        },
    }
    assert transitions_from_webhook("pull_request", payload)[0].status == "in_review"


def test_pr_opened_branch_task_id_yoksa_bos_liste():
    payload = {
        "action": "opened",
        "pull_request": {
            "number": 42,
            "updated_at": "2026-07-20T10:00:00Z",
            "user": {"login": "esma6"},
            "head": {"ref": "feature/random"},
        },
    }
    assert transitions_from_webhook("pull_request", payload) == []


def test_pr_diger_action_bos_liste():
    payload = {
        "action": "synchronize",
        "pull_request": {
            "number": 42,
            "updated_at": "2026-07-20T10:00:00Z",
            "user": {"login": "esma6"},
            "head": {"ref": "T-99-ornek-dal"},
        },
    }
    assert transitions_from_webhook("pull_request", payload) == []


# --- push ---

_PUSH_PAYLOAD = {
    "ref": "refs/heads/T-99-ornek-dal",
    "commits": [
        {
            "id": "abc123",
            "timestamp": "2026-07-20T10:00:00+03:00",
            "author": {"username": "esma6", "name": "Esma"},
            "added": ["src/backend/x.py"],
            "removed": [],
            "modified": ["README.md"],
        }
    ],
}


def test_push_branch_uretir_in_progress():
    transitions = transitions_from_webhook("push", _PUSH_PAYLOAD)
    assert len(transitions) == 1
    t = transitions[0]
    assert t.task_id == "T-99"
    assert t.status == "in_progress"
    assert t.reason == "push"


def test_push_main_bos_liste():
    payload = {"ref": "refs/heads/main", "commits": [{"id": "x", "timestamp": "2026-07-20T10:00:00Z"}]}
    assert transitions_from_webhook("push", payload) == []


def test_push_tag_bos_liste():
    payload = {"ref": "refs/tags/v1.0.0", "commits": [{"id": "x", "timestamp": "2026-07-20T10:00:00Z"}]}
    assert transitions_from_webhook("push", payload) == []


def test_bilinmeyen_event_type_bos_liste():
    assert transitions_from_webhook("ping", {"zen": "..."}) == []


# --- source_event_id, normalize.py ile birebir aynı olmalı ---


def test_source_event_id_pr_normalize_ile_ayni():
    pr = {
        "number": 42,
        "updated_at": "2026-07-20T10:00:00Z",
        "user": {"login": "esma6"},
        "head": {"ref": "T-99-ornek-dal"},
    }
    payload = {"action": "opened", "pull_request": pr}
    transition = transitions_from_webhook("pull_request", payload)[0]
    assert transition.source_event_id == pr_to_event(pr).id


def test_source_event_id_issue_normalize_ile_ayni():
    issue = {"number": 158, "updated_at": "2026-07-25T09:00:00Z", "user": {"login": "esma"}}
    payload = {"action": "closed", "issue": issue}
    transition = transitions_from_webhook("issues", payload)[0]
    assert transition.source_event_id == issue_to_event(issue).id


def test_source_event_id_commit_push_normalize_ile_ayni():
    transition = transitions_from_webhook("push", _PUSH_PAYLOAD)[0]
    normalized_event = webhook_push_to_events(_PUSH_PAYLOAD)[0]
    assert transition.source_event_id == normalized_event.id


# --- transitions_from_resources (polling/backfill, REST kaynak şekli) ---


def test_transitions_from_resources_pr_merged_done():
    prs = [
        {
            "number": 258,
            "updated_at": "2026-07-25T11:00:00Z",
            "state": "closed",
            "merged": True,
            "head": {"ref": "T-158-fix-thing"},
            "body": "",
        }
    ]
    transitions = transitions_from_resources(prs, [])
    assert len(transitions) == 1
    assert transitions[0].task_id == "T-158"
    assert transitions[0].status == "done"


def test_transitions_from_resources_pr_open_in_review():
    prs = [
        {
            "number": 42,
            "updated_at": "2026-07-20T10:00:00Z",
            "state": "open",
            "merged": False,
            "head": {"ref": "T-99-ornek-dal"},
        }
    ]
    transitions = transitions_from_resources(prs, [])
    assert len(transitions) == 1
    assert transitions[0].status == "in_review"


def test_transitions_from_resources_pr_kapali_merge_edilmemis_no_op():
    prs = [
        {
            "number": 42,
            "updated_at": "2026-07-20T10:00:00Z",
            "state": "closed",
            "merged": False,
            "head": {"ref": "T-99-ornek-dal"},
        }
    ]
    assert transitions_from_resources(prs, []) == []


def test_transitions_from_resources_issue_closed_done():
    issues = [{"number": 158, "updated_at": "2026-07-25T09:00:00Z", "state": "closed"}]
    transitions = transitions_from_resources([], issues)
    assert len(transitions) == 1
    assert transitions[0].task_id == "T-158"
    assert transitions[0].status == "done"


def test_transitions_from_resources_issue_acik_no_op():
    issues = [{"number": 158, "updated_at": "2026-07-25T09:00:00Z", "state": "open"}]
    assert transitions_from_resources([], issues) == []


def test_REST_LISTE_sekli_merged_anahtari_YOK_yalniz_merged_at():
    """#331 — GERÇEK backfill payload'ı: `GET /repos/{o}/{r}/pulls` ucu
    (`pull-request-simple`) `merged` alanını HİÇ TAŞIMAZ, yalnız `merged_at`.

    Yukarıdaki `test_transitions_from_resources_pr_merged_done` bu tuzağı
    ıskalıyordu çünkü elle `"merged": True` yazıyor — webhook'un içindeki TAM
    PR nesnesinin şekli. Ölçüldü (2026-07-30, canlı repo):
        gh api '/repos/FatihErenCetin/grup54/pulls?state=all' \
          --jq '.[] | has("merged")'  ->  hepsi false
    Yani `pr.get("merged")` tek başına bakıldığında backfill'den ÜRETİLEN
    `done` sayısı SIFIR olurdu ve bu hiçbir hata vermeden olurdu.

    MUTASYON: `status_rules._merged`'i `return bool(pr.get("merged"))`'a geri
    al -> bu test kırmızı olur (transitions boş döner).
    """
    prs = [
        {
            "number": 328,
            "updated_at": "2026-07-29T21:47:45Z",
            "state": "closed",
            "merged_at": "2026-07-29T21:47:42Z",  # `merged` anahtarı YOK — bilerek
            "head": {"ref": "T-327-severity-normalizasyonu"},
            "body": "Closes #327",
        }
    ]
    transitions = transitions_from_resources(prs, [])
    assert [t.task_id for t in transitions] == ["T-327"]
    assert transitions[0].status == "done"
    assert transitions[0].reason == "pr_merged"


def test_merged_at_null_kapali_pr_hala_no_op():
    """`merged_at: None` (merge edilmeden kapatılmış PR) `done` ÜRETMEZ —
    `_merged` gevşerken bu tarafın da tutulduğunu kilitler (aksi halde
    `merged_at in pr` gibi bir kontrol her kapalı PR'ı done sayardı)."""
    prs = [
        {
            "number": 42,
            "updated_at": "2026-07-20T10:00:00Z",
            "state": "closed",
            "merged_at": None,
            "head": {"ref": "T-99-ornek-dal"},
        }
    ]
    assert transitions_from_resources(prs, []) == []


def test_webhook_yolunda_da_merged_at_kabul_edilir():
    """`_merged` iki yolda da AYNI: webhook payload'ı (nadiren) `merged`
    taşımayıp `merged_at` taşırsa geçiş yine üretilir — iki yolun tek kural
    kullandığının kilidi."""
    payload = {
        "action": "closed",
        "pull_request": {
            "number": 328,
            "updated_at": "2026-07-29T21:47:45Z",
            "merged_at": "2026-07-29T21:47:42Z",
            "head": {"ref": "T-327-severity-normalizasyonu"},
            "body": "",
        },
    }
    transitions = transitions_from_webhook("pull_request", payload)
    assert [t.status for t in transitions] == ["done"]


# --- next_status monotonluk ---


def test_status_rank_sozlugu_donmus_api_ile_ayni():
    assert STATUS_RANK == {
        "backlog": 0,
        "todo": 1,
        "in_progress": 2,
        "in_review": 3,
        "done": 4,
    }


def test_in_review_uzerine_push_geri_oynatmaz():
    assert next_status("in_review", _t("in_progress")) == "in_review"


def test_ileri_gecis_uygulanir():
    assert next_status("todo", _t("in_progress")) == "in_progress"


def test_done_uzerine_ileri_olmayan_gecis_etkilemez():
    for status in ("backlog", "todo", "in_progress", "in_review", "done"):
        assert next_status("done", _t(status)) == "done"


def test_resets_true_done_dahil_her_seyi_geriye_alir():
    assert next_status("done", _t("todo", resets=True)) == "todo"


def test_ayni_rank_gecis_uygulanir_idempotent():
    assert next_status("in_review", _t("in_review")) == "in_review"
