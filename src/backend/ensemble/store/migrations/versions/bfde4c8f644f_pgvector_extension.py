"""Alembic migration script template for ensemble store.

pgvector extension

Revision ID: bfde4c8f644f
Revises: b636480eb1c7
Create Date: 2026-07-11 11:57:58.098620
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'bfde4c8f644f'
down_revision: Union[str, None] = 'b636480eb1c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Yalnızca PostgreSQL'de pgvector extension oluştur
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.execute("DROP EXTENSION IF EXISTS vector")
