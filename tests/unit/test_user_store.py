"""`ensemble.store.user_store` + `UserRow` testleri (T-294/D-57).

`test_verdict_store.py` ile AYNI kalıp — in-memory SQLite + `Base.metadata.
create_all`. CHECK kısıtının (`ck_users_auth_method_present`) gerçekten
uygulandığını da burada kanıtlıyoruz (mutasyon: PR gövdesinde ayrıca
CHECK'i kaldırıp bu testin kırmızıya döndüğü gösterildi).
"""

import pytest
from sqlalchemy.exc import IntegrityError

from ensemble.config import Settings
from ensemble.store.engine import get_engine, get_session_factory
from ensemble.store.models import Base, UserRow
from ensemble.store.user_store import create_user, get_user_by_email, touch_last_login


@pytest.fixture
def session():
    settings = Settings(DATABASE_URL="sqlite:///:memory:")
    engine = get_engine(settings)
    Base.metadata.create_all(engine)
    session_factory = get_session_factory(engine)
    with session_factory() as session:
        yield session


def test_create_user_ve_get_by_email_roundtrip(session):
    user = create_user(session, normalized_email="ali@x.com", password_hash="hash-1")
    session.commit()

    found = get_user_by_email(session, "ali@x.com")
    assert found is not None
    assert found.id == user.id
    assert found.email == "ali@x.com"
    assert found.password_hash == "hash-1"
    assert found.github_handle is None
    assert found.created_at is not None
    assert found.last_login_at is not None


def test_get_user_by_email_yoksa_none_doner(session):
    assert get_user_by_email(session, "hic-yok@x.com") is None


def test_create_user_benzersiz_id_uretir(session):
    u1 = create_user(session, normalized_email="a@x.com", password_hash="h1")
    u2 = create_user(session, normalized_email="b@x.com", password_hash="h2")
    session.commit()
    assert u1.id != u2.id


def test_touch_last_login_tazeler(session):
    user = create_user(session, normalized_email="ali@x.com", password_hash="hash-1")
    session.commit()
    ilk = user.last_login_at

    touch_last_login(session, user)
    session.commit()

    assert user.last_login_at >= ilk


def test_ayni_email_iki_kez_unique_kisitini_ihlal_eder(session):
    # user_store kendi başına ikinci bir get_user_by_email kontrolü YAPMAZ
    # (bu router'ın işi) — ama DB'nin UNIQUE kısıtı burada da son savunma
    # hattı olarak çalışmalı.
    create_user(session, normalized_email="ali@x.com", password_hash="h1")
    session.commit()
    with pytest.raises(IntegrityError):
        create_user(session, normalized_email="ali@x.com", password_hash="h2")
        session.commit()
    session.rollback()


# --- CHECK kısıtı: ck_users_auth_method_present ---


def test_check_kisiti_ikisi_de_null_olan_satiri_reddeder(session):
    """Mutasyon kanıtı (PR gövdesi): `UserRow.__table_args__`'taki
    CheckConstraint kaldırılıp bu test tekrar koşulduğunda satır SESSİZCE
    yazılabiliyor (kırmızı yerine yeşil) — kısıt gerçekten bu satırı
    engelliyor."""
    hayalet = UserRow(
        id="hayalet-1",
        email="hayalet@x.com",
        password_hash=None,
        github_handle=None,
    )
    session.add(hayalet)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_check_kisiti_yalniz_password_hash_doluyken_izin_verir(session):
    row = UserRow(id="only-pw", email="a@x.com", password_hash="h", github_handle=None)
    session.add(row)
    session.commit()  # patlamamalı


def test_check_kisiti_yalniz_github_handle_doluyken_izin_verir(session):
    row = UserRow(id="only-gh", email="b@x.com", password_hash=None, github_handle="esma6")
    session.add(row)
    session.commit()  # patlamamalı
