"""pgvector index table

Revision ID: c4f1d6a2b8e9
Revises: bfde4c8f644f
Create Date: 2026-07-17 17:36:00.000000
"""

from typing import Sequence, Union

from alembic import op
from ensemble.config import get_settings

# revision identifiers, used by Alembic.
revision: str = "c4f1d6a2b8e9"
down_revision: Union[str, None] = "bfde4c8f644f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None




def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        settings = get_settings()
        op.execute(
            f"""
            CREATE TABLE IF NOT EXISTS vector_index (
                id TEXT PRIMARY KEY,
                embedding vector({settings.GEMINI_EMBEDDING_DIMENSIONS}) NOT NULL,
                meta JSONB NOT NULL DEFAULT '{{}}'::jsonb
            )
            """
        )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.execute("DROP TABLE IF EXISTS vector_index")
