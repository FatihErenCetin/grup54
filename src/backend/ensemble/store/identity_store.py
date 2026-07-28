"""`identities` tablosu okuma/yazma (T-79 — çok-kiracılı repo seçimi).

`user_store.py`/`verdict_store.py` ile AYNI disiplin: yalnızca DB IO —
GitHub'dan kullanıcı bilgisi çekmeyi (integrations/github/oauth.py) BİLMEZ.

`get_or_create_github_user` GitHub OAuth callback'inin (api/routers/auth.py)
TEK çağırdığı fonksiyondur: aynı GitHub hesabı (aynı `provider_user_id`) ikinci
kez giriş yaptığında YENİ bir `UserRow` AÇMAZ, var olanı bulur. Bu, D-57'nin
"hesap birleştirme kapsam dışı" kararını GENİŞLETMEZ — email hesabıyla
otomatik birleştirme YAPILMAZ, yalnızca AYNI GitHub kimliğinin tekrar
girişinde AYNI satıra dönülür.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ensemble.store.models import IdentityRow, UserRow

GITHUB_PROVIDER = "github"


def get_identity(session: Session, *, provider: str, provider_user_id: str) -> IdentityRow | None:
    return session.scalar(
        select(IdentityRow).where(
            IdentityRow.provider == provider,
            IdentityRow.provider_user_id == provider_user_id,
        )
    )


def get_or_create_github_user(
    session: Session,
    *,
    github_user_id: str,
    handle: str,
    avatar_url: str | None,
) -> UserRow:
    """`github_user_id` (GitHub'ın SAYISAL, DEĞİŞMEYEN kullanıcı id'si —
    handle DEĞİL) üzerinden get-or-create. İlk girişte `UserRow` +
    `IdentityRow` BİRLİKTE (aynı flush) açılır; sonraki girişlerde yalnızca
    `handle`/`avatar_url` GÜNCELLENİR (GitHub'da değişmiş olabilirler),
    `id` SABİT kalır (installations/watched_repos bu id'ye bağlı)."""
    identity = get_identity(session, provider=GITHUB_PROVIDER, provider_user_id=github_user_id)
    if identity is not None:
        user = session.get(UserRow, identity.user_id)
        if user is None:
            # Kanıtlanamaz ama savunma amaçlı: identity var, user_id'si
            # işaret ettiği satır yoksa (elle silinmiş DB vb.) sessizce
            # devam etmek yerine gürültülü başarısız ol.
            raise RuntimeError(
                f"identities.user_id={identity.user_id!r} için users satırı bulunamadı (tutarsız DB)"
            )
        if user.github_handle != handle or user.avatar_url != avatar_url:
            user.github_handle = handle
            user.avatar_url = avatar_url
            session.flush()
        return user

    now = datetime.utcnow()
    user = UserRow(
        id=str(uuid.uuid4()),
        email=f"github:{github_user_id}@users.noreply.ensemble.local",
        password_hash=None,
        github_handle=handle,
        avatar_url=avatar_url,
        created_at=now,
        last_login_at=now,
    )
    session.add(user)
    session.flush()
    session.add(
        IdentityRow(
            id=str(uuid.uuid4()),
            provider=GITHUB_PROVIDER,
            provider_user_id=github_user_id,
            user_id=user.id,
            created_at=now,
        )
    )
    session.flush()
    return user
