from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from ensemble.app import create_app
from ensemble.config import Settings
from ensemble.engine.board import BoardService, compute_board_provenance
from ensemble.store.engine import get_engine, get_session_factory
from ensemble.store.models import DEFAULT_REPO_FULL_NAME, Base, TaskProjectionRow, TaskStatusEventRow
from ensemble.store.rebuild import append_status_events, rebuild_projection
from ensemble_shared.harness import HarnessPort

_REPO = DEFAULT_REPO_FULL_NAME


def test_get_board_returns_cards_successfully(tmp_path):
    db_path = tmp_path / "test_board.db"
    settings = Settings(DATABASE_URL=f"sqlite:///{db_path}")
    app = create_app(settings)

    with TestClient(app) as client:
        engine = app.state.session_factory.kw["bind"]
        Base.metadata.create_all(engine)

        with app.state.session_factory() as session:
            session.add(
                TaskProjectionRow(
                    task_id="T-51", repo_full_name=_REPO, title="Board API", status="in_progress"
                )
            )
            session.commit()

        response = client.get("/board")

        assert response.status_code == 200
        data = response.json()
        assert "cards" in data
        assert len(data["cards"]) == 1
        assert data["cards"][0]["task_id"] == "T-51"
        assert data["cards"][0]["title"] == "Board API"


def test_get_board_provenance_seed_hic_gecis_yokken(tmp_path):
    """İş 4 kabul kriteri: hiç geçiş yokken source=="seed" ve last_transition_at None.

    Bugün (İş 2 henüz merge olmadan) `TaskProjectionRow`'da `last_transition_at`
    kolonu hiç yok — bu test tam da o gerçek durumu, gerçek DB üzerinden
    doğruluyor (get_board() -> HTTP -> BoardResponse zarfı).
    """
    db_path = tmp_path / "test_board_seed.db"
    settings = Settings(DATABASE_URL=f"sqlite:///{db_path}")
    app = create_app(settings)

    with TestClient(app) as client:
        engine = app.state.session_factory.kw["bind"]
        Base.metadata.create_all(engine)

        with app.state.session_factory() as session:
            session.add(
                TaskProjectionRow(
                    task_id="T-51", repo_full_name=_REPO, title="Board API", status="in_progress"
                )
            )
            session.commit()

        response = client.get("/board")

        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "seed"
        assert data["last_transition_at"] is None


def test_gecis_sonrasi_provenance_dolu():
    """İş 4 kabul kriteri: bir geçiş uygulandıktan sonra source=="ingest" ve
    last_transition_at o olayın ts'i.

    İş 2'nin `TaskProjectionRow.last_transition_at` kolonu bu sprintte henüz
    merge edilmemiş olabilir (BAĞIMLILIK notu) — bu yüzden `compute_board_provenance`
    saf fonksiyonu, ORM'den TAMAMEN bağımsız basit stub satırlarla test edilir.
    İş 2 merge olunca gerçek `TaskProjectionRow` satırları da aynı `getattr`
    sözleşmesini karşılayacağı için davranış DEĞİŞMEZ.
    """
    older = datetime(2026, 7, 24, 10, 0, 0)
    newest = datetime(2026, 7, 26, 9, 30, 0)
    rows = [
        SimpleNamespace(task_id="T-51", last_transition_at=None),
        SimpleNamespace(task_id="T-158", last_transition_at=older),
        SimpleNamespace(task_id="T-258", last_transition_at=newest),
    ]

    last_transition_at, source = compute_board_provenance(rows)

    assert source == "ingest"
    assert last_transition_at == newest


def test_get_board_provenance_ingest_gercek_fold_sonrasi():
    """İş 4 kabul kriteri, GERÇEK yol (İş 2 bu sprintte merge oldu): rebuild_projection
    ile GERÇEK bir GitHub-türevi geçiş (task_status_events) katlandıktan sonra
    BoardService.get_board() source=="ingest" ve last_transition_at == o
    geçişin ts'i döner. Stub tabanlı test_gecis_sonrasi_provenance_dolu'nun
    aksine burada ORM/DB/rebuild_projection uçtan uca gerçek."""
    settings = Settings(DATABASE_URL="sqlite:///:memory:")
    engine = get_engine(settings)
    Base.metadata.create_all(engine)
    session_factory = get_session_factory(engine)

    harness = MagicMock(spec=HarnessPort)
    harness.read_tasks.return_value = [{"task_id": "T-158", "title": "Health zinciri", "status": "todo"}]
    harness.read_active.return_value = []

    event_ts = datetime(2026, 7, 25, 12, 0)
    with session_factory() as session:
        append_status_events(
            session,
            [
                TaskStatusEventRow(
                    source_event_id="issue-258-closed",
                    task_id="T-158",
                    repo_full_name=_REPO,
                    status="done",
                    ts=event_ts,
                    reason="issue_closed",
                )
            ],
        )
        session.commit()
        rebuild_projection(session, harness)

    board = BoardService(session_factory=session_factory).get_board()

    assert board.source == "ingest"
    assert board.last_transition_at == event_ts
    assert board.cards[0].status == "done"


def test_gecis_yokken_provenance_seed():
    """Aynı saf fonksiyonun "hiç geçiş yok" dalı — hiçbir satırda
    last_transition_at set değilken (bugünkü gerçek durum) source=="seed"."""
    rows = [
        SimpleNamespace(task_id="T-51", last_transition_at=None),
        TaskProjectionRow(task_id="T-52", title="x", status="todo"),  # gerçek ORM satırı, kolon YOK
    ]

    last_transition_at, source = compute_board_provenance(rows)

    assert source == "seed"
    assert last_transition_at is None
