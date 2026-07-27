"""`ensemble.store.verdict_store` testleri (#259, GÖREV 1/2).

Kalıcı judge yargı deposu: yazma/okuma, idempotent upsert, bozuk/eski
şemalı satırın sessizce (ama log'lu) `None` dönmesi. `test_store_engine.py`
ile aynı kalıp — in-memory SQLite + `Base.metadata.create_all`.
"""

from datetime import datetime, timedelta

import pytest

from ensemble.config import Settings
from ensemble.models import Detection
from ensemble.store.engine import get_engine, get_session_factory
from ensemble.store.models import Base, JudgeVerdictRow
from ensemble.store.verdict_store import get_verdict, put_verdict


@pytest.fixture
def session():
    settings = Settings(DATABASE_URL="sqlite:///:memory:")
    engine = get_engine(settings)
    Base.metadata.create_all(engine)
    session_factory = get_session_factory(engine)
    with session_factory() as session:
        yield session


def _detection(id_: str = "d1") -> Detection:
    return Detection(
        id=id_,
        actors=["esma6", "EnesErdemT"],
        branches=["T-259-a", "T-259-b"],
        files=["src/backend/ensemble/engine/cache.py"],
        severity="high",
        confidence=0.9,
        rationale="aynı dosyada eşzamanlı geniş kapsamlı değişiklik",
    )


def test_get_verdict_miss_yoksa_none_doner(session):
    # Hiç yazılmamış bir cache_key — gerçek MISS, alt porta gidilmeli.
    assert get_verdict(session, "hic-yok") is None


def test_put_ve_get_verdict_roundtrip(session):
    detection = _detection()
    put_verdict(session, "key-1", "gemini-1.5-flash", detection)
    session.commit()

    restored = get_verdict(session, "key-1")
    assert restored == detection

    row = session.get(JudgeVerdictRow, "key-1")
    assert row is not None
    assert row.model == "gemini-1.5-flash"
    assert isinstance(row.created_at, datetime)


def test_put_verdict_idempotent_upsert_satir_cogalmiyor(session):
    # Aynı cache_key ikinci kez yazılırsa (eş zamanlı iki isteğin aynı
    # MISS'i alt porta göndermesi gibi) satır ÇOĞALMAZ, üzerine yazılır.
    first = _detection("d1")
    put_verdict(session, "key-1", "gemini-1.5-flash", first)
    session.commit()

    second = _detection("d1")
    second.severity = "low"
    second.confidence = 0.4
    put_verdict(session, "key-1", "gemini-2.0-flash", second)
    session.commit()

    assert session.query(JudgeVerdictRow).count() == 1

    restored = get_verdict(session, "key-1")
    assert restored == second

    row = session.get(JudgeVerdictRow, "key-1")
    assert row.model == "gemini-2.0-flash"


def test_farkli_model_farkli_cache_key_ile_ayri_satir_tutulur(session):
    # `model` anahtara KATILMIŞ olmalı (çağıranın sorumluluğu) — bu
    # testte iki farklı cache_key iki farklı model için ayrı satır olarak
    # tutulduğunu doğrular (aynı cache_key'in üzerine yazılmadığını).
    detection_a = _detection("d1")
    detection_b = _detection("d1")
    detection_b.severity = "low"

    put_verdict(session, "key-gemini", "gemini-1.5-flash", detection_a)
    put_verdict(session, "key-groq", "llama-3.3-70b", detection_b)
    session.commit()

    assert session.query(JudgeVerdictRow).count() == 2
    assert get_verdict(session, "key-gemini") == detection_a
    assert get_verdict(session, "key-groq") == detection_b


def test_bozuk_satir_sessizce_none_doner(session):
    # Eski/bozuk şemalı bir satır (Detection'a UYMAYAN JSON) elle eklenir —
    # get_verdict() bunu bir programlama hatası gibi patlatmaz, MEŞRU bir
    # geçiş yolu olarak None döner (yargı yeniden hesaplanacak).
    bozuk = JudgeVerdictRow(
        cache_key="bozuk-key",
        model="eski-model",
        detection={"beklenmeyen": "sema"},
        created_at=datetime(2026, 1, 1),
    )
    session.add(bozuk)
    session.commit()

    assert get_verdict(session, "bozuk-key") is None


def test_bozuk_satirin_ustune_put_verdict_ile_yeniden_yazilabilir(session):
    # Bayat şemalı satır tespit edildikten sonra aynı cache_key ile taze
    # bir yargı yazılırsa (yeniden hesaplama sonrası) satır güncel şemaya
    # döner — get_verdict() artık normal roundtrip yapar.
    bozuk = JudgeVerdictRow(
        cache_key="bozuk-key",
        model="eski-model",
        detection={"beklenmeyen": "sema"},
        created_at=datetime(2026, 1, 1),
    )
    session.add(bozuk)
    session.commit()
    assert get_verdict(session, "bozuk-key") is None

    taze = _detection("d1")
    put_verdict(session, "bozuk-key", "gemini-1.5-flash", taze)
    session.commit()

    assert get_verdict(session, "bozuk-key") == taze
    assert session.query(JudgeVerdictRow).count() == 1


def test_ttl_days_verilmezse_kontrol_yapilmaz_gecmis_satir_yine_hit(session):
    """`ttl_days=None` (varsayılan) — #264 öncesi çağıranlarla (bu dosyanın
    yukarıdaki testleri) geriye dönük uyumluluk: süre kontrolü hiç
    YAPILMAZ, `created_at` ne kadar eski olursa olsun satır HIT sayılır."""
    detection = _detection("cok-eski-ama-ttl-kontrolsuz")
    put_verdict(session, "key-1", "gemini-1.5-flash", detection)
    session.commit()

    row = session.get(JudgeVerdictRow, "key-1")
    row.created_at = datetime(2000, 1, 1)
    session.commit()

    assert get_verdict(session, "key-1") == detection


def test_ttl_gecmis_satir_none_doner(session):
    """Semih blocker B (#264): `ttl_days` verilince ve satır bu süreden
    daha eskiyse `get_verdict` `None` DÖNER (MEŞRU MISS — bozuk şema
    durumuyla aynı aile, satır fiziksel olarak var ama artık geçersiz).

    MUTASYON KİLİDİ: TTL karşılaştırmasını kaldır (ya da `<` yerine hep
    `False` dön) -> bu test KIRILIR, eski yargı sessizce HIT sayılır."""
    detection = _detection("suresi-dolmus")
    put_verdict(session, "key-1", "gemini-1.5-flash", detection)
    session.commit()

    row = session.get(JudgeVerdictRow, "key-1")
    row.created_at = datetime.utcnow() - timedelta(days=8)
    session.commit()

    assert get_verdict(session, "key-1", ttl_days=7) is None
    # Satır SİLİNMEDİ - yalnızca okunmadı (bkz. get_verdict docstring'i).
    assert session.query(JudgeVerdictRow).count() == 1


def test_ttl_icindeki_satir_hit_doner(session):
    """Regresyon karşıtı: TTL süresi İÇİNDEKİ bir satır normal HIT olarak
    döner — TTL eklemek süresi dolmamış satırları BOZMAMALI."""
    detection = _detection("henuz-taze")
    put_verdict(session, "key-1", "gemini-1.5-flash", detection)
    session.commit()

    row = session.get(JudgeVerdictRow, "key-1")
    row.created_at = datetime.utcnow() - timedelta(days=1)
    session.commit()

    assert get_verdict(session, "key-1", ttl_days=7) == detection


def test_put_verdict_uzerine_yazinca_created_at_tazelenir(session):
    """#264 blocker B'nin ikinci yarısı: `created_at` yalnızca İLK INSERT'te
    değil, bir mevcut satırın ÜZERİNE yazılırken de tazelenmeli — aksi
    halde TTL'i bir kez dolan satır, yeniden hesaplanıp yazılsa bile
    SONSUZA dek "süresi dolmuş" kalır (sonsuz MISS döngüsü).

    MUTASYON KİLİDİ: `put_verdict` içinde `row.created_at = now` atamasını
    kaldır (UPDATE dalında) -> bu test KIRILIR (`created_at` eski tarihte
    donmuş kalır)."""
    detection = _detection("ilk-yazim")
    put_verdict(session, "key-1", "gemini-1.5-flash", detection)
    session.commit()

    row = session.get(JudgeVerdictRow, "key-1")
    row.created_at = datetime.utcnow() - timedelta(days=30)
    session.commit()

    yeni_detection = _detection("ikinci-yazim-ttl-sonrasi")
    put_verdict(session, "key-1", "gemini-1.5-flash", yeni_detection)
    session.commit()

    row = session.get(JudgeVerdictRow, "key-1")
    assert row.created_at > datetime.utcnow() - timedelta(minutes=1)
    # Tazelenmiş created_at ile artık HIT (TTL içinde).
    assert get_verdict(session, "key-1", ttl_days=7) == yeni_detection
