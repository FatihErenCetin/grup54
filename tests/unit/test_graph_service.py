from datetime import datetime, timedelta, timezone

from ensemble.config import Settings
from ensemble.engine.graph import GraphService
from ensemble.store.engine import get_engine, get_session_factory
from ensemble.store.models import Base, EventRow


def _session_factory():
    engine = get_engine(Settings(DATABASE_URL="sqlite:///:memory:"))
    Base.metadata.create_all(engine)
    return get_session_factory(engine)


class _FakeHarnessPort:
    def __init__(self, actives: list[dict]):
        self._actives = actives

    def read_active(self) -> list[dict]:
        return self._actives


def test_get_graph_db_projeksiyonundan_uretir():
    session_factory = _session_factory()
    with session_factory() as session:
        session.add(
            EventRow(
                id="e1",
                type="commit",
                actor="enes",
                branch="main",
                files=["src/backend/a.py"],
                ts=datetime.now(timezone.utc),
                ref="abc123",
            )
        )
        session.commit()

    # Fatih review bulgusu (HIGH): active_pairs artik PresenceRow.module
    # (serbest-form, orn. "store") DEGIL, .harness/active/*'in paths'inden
    # _module_of ile TURETILIR - kenarlarla ayni namespace ("backend").
    harness = _FakeHarnessPort([{"handle": "enes", "paths": ["src/backend/a.py"]}])
    service = GraphService(session_factory, harness_port=harness)
    graph = service.get_graph()

    assert any(n.id == "enes" and n.type == "actor" for n in graph.nodes)
    assert any(n.id == "backend" and n.type == "module" for n in graph.nodes)
    edge = next(e for e in graph.edges if e.actor == "enes" and e.module == "backend")
    assert edge.is_active_declared is True


def test_get_graph_namespace_uyusmazligi_artik_yok():
    """Fatih'in repro'su: event path'i 'src/backend/models.py' -> module
    'backend'; active beyani 'src/backend/config.py' dosyasina dokunuyor ->
    AYNI _module_of ile 'backend' - artik dogru eslesiyor (once serbest-form
    'module' alanindan farkli bir string olabildigi icin hep False'tu)."""
    session_factory = _session_factory()
    with session_factory() as session:
        session.add(
            EventRow(
                id="e1", type="commit", actor="enes", branch="main",
                files=["src/backend/models.py"], ts=datetime.now(timezone.utc), ref="abc",
            )
        )
        session.commit()

    harness = _FakeHarnessPort([{"handle": "enes", "paths": ["src/backend/config.py"]}])
    service = GraphService(session_factory, harness_port=harness)
    graph = service.get_graph()

    edge = next(e for e in graph.edges if e.actor == "enes" and e.module == "backend")
    assert edge.is_active_declared is True


def test_get_graph_active_beyani_yoksa_false():
    session_factory = _session_factory()
    with session_factory() as session:
        session.add(
            EventRow(
                id="e1", type="commit", actor="enes", branch="main",
                files=["src/backend/a.py"], ts=datetime.now(timezone.utc), ref="abc",
            )
        )
        session.commit()

    service = GraphService(session_factory, harness_port=_FakeHarnessPort([]))
    graph = service.get_graph()

    edge = next(e for e in graph.edges if e.actor == "enes" and e.module == "backend")
    assert edge.is_active_declared is False


def test_get_graph_pencere_disindaki_eventi_disliyor():
    session_factory = _session_factory()
    eski = datetime.now(timezone.utc) - timedelta(days=30)
    with session_factory() as session:
        session.add(
            EventRow(
                id="e-eski",
                type="commit",
                actor="enes",
                branch="main",
                files=["src/backend/a.py"],
                ts=eski,
                ref="abc123",
            )
        )
        session.commit()

    service = GraphService(session_factory, window_days=14)
    graph = service.get_graph()

    assert graph.nodes == []
    assert graph.edges == []


def test_get_graph_window_days_parametresi_override_eder():
    session_factory = _session_factory()
    service = GraphService(session_factory, window_days=14)
    graph = service.get_graph(window_days=7)
    assert graph.window_days == 7
