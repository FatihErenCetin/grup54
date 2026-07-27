"""users table

Email + parola ile gerçek üyelik (T-294/D-57) — `users` tablosu. GitHub
OAuth'un YANINDA, onun yerine değil; iki kimlik yolu paralel yaşar
(`password_hash` NULL => yalnız-GitHub, `github_handle` NULL => yalnız-email).
CHECK kısıtı ikisinin BİRDEN NULL olduğu bir satırı reddeder — kimlik
doğrulama yolu olmayan hayalet hesap DB'ye yazılamaz. Bkz.
ensemble.store.models.UserRow, `.harness/decisions/D-57-email-parola-uyeligi.md`.

Revision ID: 9aa33a394b2d
Revises: 3e1e00e45b4c
Create Date: 2026-07-28 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9aa33a394b2d"
# 3e1e00e45b4c (judge_verdicts) bugün TEK head — bu migration onun ÜSTÜNE
# zincirlenir. Başka bir revizyona (örn. d1a7c3e90f42) bağlanırsa alembic İKİ
# head görür ve `upgrade head` belirsizleşir (bkz. 3e1e00e45b4c'in kendi
# docstring'indeki aynı uyarı — bugün bir migration fork'u yaşandığı için
# bilhassa önemli).
down_revision: Union[str, None] = "3e1e00e45b4c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("github_handle", sa.String(length=255), nullable=True),
        sa.Column("avatar_url", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "password_hash IS NOT NULL OR github_handle IS NOT NULL",
            name="ck_users_auth_method_present",
        ),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(
        op.f("ix_users_github_handle"), "users", ["github_handle"], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_users_github_handle"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
