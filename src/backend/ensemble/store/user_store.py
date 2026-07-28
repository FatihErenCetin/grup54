"""`users` tablosu okuma/yazma (T-294/D-57) — email + parola üyelik.

`verdict_store.py` ile AYNI disiplin: bu modül YALNIZCA DB okuma/yazma
sınırını taşır — email normalizasyonunu, parola politikasını, hash'lemeyi
BİLMEZ (hepsi `ensemble.api.credentials`'ın işi). Fonksiyonlar ZATEN
normalize edilmiş bir `normalized_email` BEKLER, kendileri normalize ETMEZ —
iki farklı normalize noktası olsaydı aynı kişi için iki satır açılabilirdi
(#294 brifingi madde 2); TEK normalize kaynağı router katmanında bir kez
çağrılır, buraya hazır geçirilir.

`create_user`/`touch_last_login` `session.commit()` ÇAĞIRMAZ — session'ın
sahibi (çağıran router) commit eder (verdict_store.py ile aynı desen).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ensemble.store.models import UserRow


def get_user_by_email(session: Session, normalized_email: str) -> UserRow | None:
    """`normalized_email` ZATEN normalize edilmiş olmalı (bkz. modül
    docstring'i) — burada bir daha normalize EDİLMEZ."""
    return session.scalar(select(UserRow).where(UserRow.email == normalized_email))


def get_user_by_id(session: Session, user_id: str) -> UserRow | None:
    """T-79 (çok-kiracılık): `TenantDep` oturumdaki `sub` (users.id) üzerinden
    aktif repoyu/kurulumları çözerken kullanır."""
    return session.get(UserRow, user_id)


def set_active_repo(session: Session, user: UserRow, repo_full_name: str | None) -> None:
    """`PUT /auth/repos`'un `active` alanını yazar (T-79). Çağıran ÖNCE
    `repo_full_name`'in bu kullanıcının `watched_repos` kümesinde olduğunu
    doğrulamalı — bu fonksiyon doğrulama YAPMAZ, yalnızca yazar (verdict_store.py
    ile aynı disiplin: DB IO burada, iş kuralı router'da)."""
    user.active_repo_full_name = repo_full_name
    session.flush()


def create_user(session: Session, *, normalized_email: str, password_hash: str) -> UserRow:
    """Yeni email+parola hesabı ekler (id üretimi burada — uuid4).

    Çağıran (router) BENZERSİZLİK kontrolünü (`get_user_by_email` ile) bu
    çağrıdan ÖNCE yapmalı; DB'nin kendi `email` UNIQUE kısıtı yine de son
    savunma hattıdır (eşzamanlı iki kayıt yarışı — çağıran `IntegrityError`'ı
    yakalayıp 409'a çevirir, bu fonksiyon onu YUTMAZ).
    """
    now = datetime.utcnow()
    user = UserRow(
        id=str(uuid.uuid4()),
        email=normalized_email,
        password_hash=password_hash,
        created_at=now,
        last_login_at=now,
    )
    session.add(user)
    session.flush()
    return user


def touch_last_login(session: Session, user: UserRow) -> None:
    """Başarılı `/auth/login`'de çağrılır — `last_login_at`'ı şimdiye tazeler."""
    user.last_login_at = datetime.utcnow()
    session.flush()
