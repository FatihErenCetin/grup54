"""`installations` + `watched_repos` tabloları okuma/yazma (T-79 — çok-kiracılı
repo seçimi). `user_store.py`/`verdict_store.py` ile AYNI disiplin: yalnızca DB
IO — GitHub API çağrılarını (installation-token üretimi, repo listeleme)
BİLMEZ, bunlar `api/routers/auth.py`'nin işi.

Kalıcı token BURADA DA SAKLANMAZ — `InstallationRow` yalnızca `installation_id`
(GitHub'ın verdiği, kalıcı ama SIR OLMAYAN kimlik) + hangi kullanıcının
kurduğu bilgisini taşır.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ensemble.store.models import InstallationRow, WatchedRepoRow


def upsert_installation(
    session: Session, *, installation_id: str, account_login: str, user_id: str
) -> InstallationRow:
    """Aynı `installation_id` ikinci kez görülürse (örn. kullanıcı App'i
    tekrar kurdu/güncelledi) satır GÜNCELLENİR, ÇOĞALTILMAZ."""
    row = session.get(InstallationRow, installation_id)
    if row is not None:
        row.account_login = account_login
        row.user_id = user_id
        session.flush()
        return row

    row = InstallationRow(
        installation_id=installation_id,
        account_login=account_login,
        user_id=user_id,
        created_at=datetime.utcnow(),
    )
    session.add(row)
    session.flush()
    return row


def list_installations_for_user(session: Session, user_id: str) -> list[InstallationRow]:
    return list(
        session.scalars(
            select(InstallationRow).where(InstallationRow.user_id == user_id)
        ).all()
    )


def get_installation(session: Session, installation_id: str) -> InstallationRow | None:
    return session.get(InstallationRow, installation_id)


def get_installation_for_user(
    session: Session, *, user_id: str, installation_id: str
) -> InstallationRow | None:
    """`installation_id` VERİLEN kullanıcıya mı ait — yetki kontrolü için
    (bir kullanıcı BAŞKASININ installation_id'sini kullanamaz)."""
    row = session.get(InstallationRow, installation_id)
    if row is None or row.user_id != user_id:
        return None
    return row


def list_watched_repos(session: Session, user_id: str) -> list[WatchedRepoRow]:
    return list(
        session.scalars(
            select(WatchedRepoRow).where(WatchedRepoRow.user_id == user_id)
        ).all()
    )


def get_watched_repo(session: Session, *, user_id: str, repo_full_name: str) -> WatchedRepoRow | None:
    return session.get(WatchedRepoRow, (user_id, repo_full_name))


def replace_watched_repos(
    session: Session,
    *,
    user_id: str,
    repos: list[tuple[str, str]],
) -> None:
    """Kullanıcının izlediği repo setini TAMAMEN `repos` ile DEĞİŞTİRİR
    (`PUT /auth/repos` semantiği — istemcinin gönderdiği liste NİHAİ set'tir).

    `repos`: `(repo_full_name, installation_id)` çiftleri — ÇAĞIRAN (router)
    her `repo_full_name`'in `installation_id`'nin GERÇEKTEN bu kullanıcıya ait
    bir kurulumda erişilebilir olduğunu ÖNCEDEN doğrulamış olmalı (bu fonksiyon
    yalnızca YAZAR, yetki kontrolü yapmaz — verdict_store.py ile aynı ayrım).
    """
    session.query(WatchedRepoRow).filter_by(user_id=user_id).delete()
    now = datetime.utcnow()
    for repo_full_name, installation_id in repos:
        session.add(
            WatchedRepoRow(
                user_id=user_id,
                repo_full_name=repo_full_name,
                installation_id=installation_id,
                created_at=now,
            )
        )
    session.flush()
