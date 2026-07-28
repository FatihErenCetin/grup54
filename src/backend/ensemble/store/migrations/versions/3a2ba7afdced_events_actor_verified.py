"""events actor_verified

Aktör doğrulama (#296, T-296) — `events.actor_verified` kolonu:
`NormalizedEvent.actor_verified`'in DB projeksiyonu (bkz. store/models.py
`EventRow` docstring'i). GitHub commit yazarı bir GitHub hesabıyla
(`author.login` / webhook `author.username`) eşleşmediğinde ham git commit
yazar adına düşülür — bu artık görünür (bkz. integrations/github/normalize.py).

`server_default=true` BİLİNÇLİ — mevcut satırlar (canlıda #296'nın işaret
ettiği 11 eşleşmeyen satır DAHİL, PO kararı: bu satırlara ŞİMDİLİK
dokunulmuyor) "doğrulanmış" varsayılanına düşer; geçmiş yeniden
YORUMLANMAZ, yalnızca BUNDAN SONRAKİ ingest gerçek sinyali taşır.

Revision ID: 3a2ba7afdced
Revises: a1f7c9d4e2b6
Create Date: 2026-07-28 14:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3a2ba7afdced"
# a1f7c9d4e2b6 (çok-kiracılı repo seçimi) bugün TEK head — bu migration onun
# ÜSTÜNE zincirlenir (bkz. o migration'ın kendi docstring'indeki aynı uyarı;
# bu repoda daha önce bir migration fork'u yaşandığı için `alembic heads`
# İLE DOĞRULANMADAN yeni bir migration'ın down_revision'ı belirlenmemeli).
down_revision: Union[str, None] = "a1f7c9d4e2b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch_alter_table: SQLite'ta tablo-yeniden-oluşturma ile, Postgres'te
    # düz ALTER TABLE ile — tek kod yolu iki dialekte de çalışır (bkz.
    # d1a7c3e90f42 aynı desen). `server_default=true()` mevcut satırları
    # (NOT NULL ihlali olmadan) "doğrulanmış" a backfill eder.
    with op.batch_alter_table("events") as batch_op:
        batch_op.add_column(
            sa.Column(
                "actor_verified",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("events") as batch_op:
        batch_op.drop_column("actor_verified")
