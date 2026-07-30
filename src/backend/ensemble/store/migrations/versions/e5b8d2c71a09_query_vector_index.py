"""Ask korpusuna AYRI vektör tablosu (query_vector_index) — #355

NEDEN AYRI TABLO (canlıda ölçülen sessiz hata, 30 Tem 2026):

Radar ile Ask aynı `vector_index` tablosunu paylaşıyordu. Radar'ın yeniden
kurulumu (`store/rebuild.py`) `vector_index.replace_all(...)` çağırıyor —
sözleşmesi gereği tabloyu KOMPLE silip yalnız radar'ın hazırladığı olay
vektörlerini yazıyor. Sonuç: Ask'ın `scope` / `task` / `decision` belge
vektörleri her rebuild'de SESSİZCE siliniyordu.

Sessiz olmasının sebebi: `QueryService._indexed_hashes` bellekte tutuluyor,
yani süreç "bu belgeleri zaten gömdüm" sanıp yeniden gömmüyor; vektör
sorgusu yalnız olay id'leri döndürüyor, Ask korpusuna filtrelenince boş
kalıyor ve **istisna fırlamadığı için `degraded` de dolmuyordu**. Ürün tam
yetenek iddia ederken leksikal çalışıyordu.

Ölçüm (canlı): `vector_index` 661 satır — 378 commit + 149 pr + 134 issue,
Ask korpusundan (`task:` / `scope:` / `decision:`) **0 satır**. "Sprint 3
kapsamında neler var?" sorusunun beş atfının da ham commit SHA'sı olmasının
sebebi buydu: semantik olarak yalnız olaylar vardı.

Neden `replace_all`'ı daraltmak DEĞİL: sözleşmesi "hepsini değiştir" ve
radar için doğru olan da bu. İki korpusun yaşam döngüsü farklı (radar'ınki
tamamen yeniden kurulur, Ask'ınki artımlı tazelenir) — farklı yaşam
döngüsü, farklı tablo.

Revision ID: e5b8d2c71a09
Revises: 3a2ba7afdced
Create Date: 2026-07-30 20:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
from ensemble.config import get_settings

# revision identifiers, used by Alembic.
revision: str = "e5b8d2c71a09"
down_revision: Union[str, None] = "3a2ba7afdced"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        # `vector_index` gibi bu tablo da yalnız hosted (pgvector) modda var;
        # local mod FAISS kullanır (bkz. c4f1d6a2b8e9 aynı koşul).
        return
    settings = get_settings()
    # Şekil `vector_index` ile BİREBİR aynı (a1f7c9d4e2b6 sonrası hâli):
    # composite PK (id, repo_full_name) — id tek başına global benzersiz
    # DEĞİL, "task:T-51" her repoda ayrı bir görevdir.
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS query_vector_index (
            id TEXT NOT NULL,
            repo_full_name TEXT NOT NULL,
            embedding vector({settings.GEMINI_EMBEDDING_DIMENSIONS}) NOT NULL,
            meta JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            PRIMARY KEY (id, repo_full_name)
        )
        """
    )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.execute("DROP TABLE IF EXISTS query_vector_index")
