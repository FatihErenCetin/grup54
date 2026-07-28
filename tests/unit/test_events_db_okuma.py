"""#265: /events tek-tüketimlik porta bağlı DEĞİL — her istemci dolu feed görür."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ensemble.engine.events import EventService
from ensemble.models import NormalizedEvent
from ensemble.store.models import DEFAULT_REPO_FULL_NAME, Base, EventRow
from ensemble_shared.harness import FileHarnessPort

_REPO = DEFAULT_REPO_FULL_NAME


class _TekTuketimlikGitHub:
    """`GitHubAdapter._seen_ids` davranışını taklit eder: aynı event'i BİR KEZ verir.

    Bu, ingest için DOĞRU bir davranış ama HTTP
    okuma yolu için felaket: tarayıcı A feed'i alır, tarayıcı B boş görür.
    """

    def __init__(self, events):
        self._kalan = list(events)
        self.calls = 0

    def fetch_events(self, since):
        self.calls += 1
        veri, self._kalan = self._kalan, []
        return veri

    def fetch_backfill_events(self, limit_per_type=50):
        return []

    def compare(self, base, head):
        return []

    def get_diff(self, base, head):
        return {}


def _ev(i, actor):
    return NormalizedEvent(
        id=f"e{i}", type="commit", actor=actor, branch=f"T-{i}",
        files=["src/x.py"], ts=datetime.now(timezone.utc) - timedelta(minutes=i), ref=f"r{i}",
    )


def _kurulum():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SF = sessionmaker(bind=engine)
    olaylar = [_ev(3, "esma"), _ev(2, "fatih"), _ev(1, "enes")] # 3: eski, 1: yeni (artan sırada eklensin ki max_ts test edilebilsin)
    with SF() as s:
        for e in olaylar:
            s.add(EventRow(id=e.id, repo_full_name=_REPO, type=e.type, actor=e.actor, branch=e.branch,
                           files=e.files, ts=e.ts.replace(tzinfo=None), ref=e.ref))
        s.commit()
    return SF, olaylar


def test_ardisik_istemciler_hepsi_dolu_feed_gorur():
    """MUTASYON KİLİDİ: session_factory dalını kaldır (hep github_port'a git)
    -> ikinci ve üçüncü çağrı BOŞ döner, bu test kırılır."""
    SF, olaylar = _kurulum()
    gh = _TekTuketimlikGitHub(olaylar)
    svc = EventService(harness_port=FileHarnessPort(), github_port=gh, session_factory=SF)
    since = datetime.now(timezone.utc) - timedelta(hours=1)

    sonuclar = [len(svc.get_events(since=since)[0]) for _ in range(3)]

    assert sonuclar == [3, 3, 3]
    assert gh.calls == 0  # DB varken GitHub'a HİÇ gidilmez


def test_session_factory_yoksa_eski_yola_duser():
    """Geriye dönük uyum: DB verilmezse mevcut davranış korunur."""
    _, olaylar = _kurulum()
    gh = _TekTuketimlikGitHub(olaylar)
    svc = EventService(harness_port=FileHarnessPort(), github_port=gh, session_factory=None)
    since = datetime.now(timezone.utc) - timedelta(hours=1)

    ilk = len(svc.get_events(since=since)[0])

    assert ilk == 3
    assert gh.calls == 1


def test_etag_tum_db_uzerinden_hesaplanir():
    """Semih blocker: ETag yalnizca since ile filtreli donen payload uzerinden degil,
    tum DB snapshot'indan bagimsiz hesaplanmali. Yoksa gec gelen eski olaylar
    client 304 aldigi icin kacar."""
    SF, olaylar = _kurulum()
    gh = _TekTuketimlikGitHub(olaylar)
    svc = EventService(harness_port=FileHarnessPort(), github_port=gh, session_factory=SF)
    
    since = datetime.now(timezone.utc)
    
    # 1. Tum feed ETag'i alalim
    _, _, etag1 = svc.get_events(since=since)
    
    # 2. DB'ye eski bir olay ekleyelim (since'den daha eski)
    with SF() as s:
        yeni = _ev(10, "gec_gelen") # 10 dakika eski
        s.add(EventRow(id=yeni.id, repo_full_name=_REPO, type=yeni.type, actor=yeni.actor, branch=yeni.branch,
                       files=yeni.files, ts=yeni.ts.replace(tzinfo=None), ref=yeni.ref))
        s.commit()
        
    # 3. Tekrar ayni cursor (since) ile soralim
    _, _, etag2 = svc.get_events(since=since)
    
    # ETag degismis OLMALI! (Cunku DB state degisti)
    assert etag1 != etag2
