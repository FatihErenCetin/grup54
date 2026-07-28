"""multi tenant repo selection

Çok-kiracılı repo seçimi (#79 kalan dilim, T-79) — `.harness/decisions/
D-58-cok-kiracili-repo-secimi.md`:

1) Yeni tablolar: `identities` (sağlayıcı kimliği -> users.id) ·
   `installations` (kurulan GitHub App'ler, kalıcı token YOK — yalnız
   installation_id) · `watched_repos` (kullanıcının izlediği repo seti).
2) `users.active_repo_full_name` — kullanıcının o an aktif kiracısı.
3) Mevcut 5 projeksiyon tablosuna (`events`, `task_projection`, `presence`,
   `task_status_events`, `vector_index`) `repo_full_name` — BİLEREK birincil
   anahtarın PARÇASI (bkz. store/models.py docstring'leri — PR/issue/task
   numaraları repo başına sıfırlanır, yalnızca kolon eklemek iki kiracının
   aynı id'yi paylaşmasına/sessiz üzerine-yazmaya yol açardı).

BACKFILL SIRASI ÖNEMLİ (canlıda 700+ satır var): önce nullable kolon ekle,
SONRA mevcut satırları `GITHUB_REPO_OWNER/GITHUB_REPO_NAME`'e (demo repo)
backfill et, EN SON NOT NULL yap. Ham `ALTER ... NOT NULL` backfill'siz
koşulursa mevcut satırlar NULL kalır ve migration canlıda patlar.

`events`/`task_projection`/`presence`/`task_status_events` composite PK'ye
geçtiği için (SQLite bir kolonu sonradan PK'ye EKLEMEYİ desteklemiyor, batch
recreate de mevcut PK ile çakışabiliyor) bu dört tablo açıkça
rename->create->copy->drop ile yeniden kurulur — veri KAYBOLMAZ (INSERT
... SELECT ile taşınır), yalnızca şekil değişir. `vector_index` yalnızca
PostgreSQL'de var (hosted) — orada düz ALTER + PK değişimi yeterli.

Revision ID: a1f7c9d4e2b6
Revises: 9aa33a394b2d
Create Date: 2026-07-28 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1f7c9d4e2b6"
# 9aa33a394b2d (users tablosu) bugün TEK head — bu migration onun ÜSTÜNE
# zincirlenir (bkz. o migration'ın kendi docstring'indeki aynı uyarı).
down_revision: Union[str, None] = "9aa33a394b2d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UNKNOWN_DEMO_REPO = "unknown/unknown"


def _demo_repo_full_name() -> str:
    """Backfill hedefi — mevcut (tek-kiracılı dönemden kalma) satırlar bu
    repoya ait sayılır. `c4f1d6a2b8e9`'un `get_settings()` kullanma deseniyle
    aynı. Ayarlar boşsa (örn. temiz bir CI/test DB'sinde) migration'ın
    çökmemesi için belgeli bir placeholder'a düşülür — gerçek dağıtımda
    `GITHUB_REPO_OWNER`/`GITHUB_REPO_NAME` zaten zorunlu tutuluyor.
    """
    from ensemble.config import get_settings

    settings = get_settings()
    return settings.demo_repo_full_name or _UNKNOWN_DEMO_REPO


def _rebuild_with_tenant_pk(
    *,
    table_name: str,
    columns: list[sa.Column],
    pk_columns: list[str],
    indexes: list[tuple[str, list[str]]],
    copy_columns: list[str],
    demo_repo: str,
) -> None:
    """`table_name`'i (id, repo_full_name gibi) YENİ bir composite PK ile
    yeniden kurar; mevcut satırlar `repo_full_name=demo_repo` ile taşınır.

    Adımlar (tek migration script'i içinde, tek transaction'da):
      1) tabloyu `<table>_t79_old` adına yeniden adlandır
      2) yeni şekli `table_name` adıyla kur (composite PK dahil)
      3) `INSERT ... SELECT` ile eski satırları + sabit `demo_repo` değerini kopyala
      4) eski tabloyu sil
      5) indeksleri yeniden kur
    """
    old_name = f"{table_name}_t79_old"
    op.rename_table(table_name, old_name)
    op.create_table(table_name, *columns, sa.PrimaryKeyConstraint(*pk_columns))

    select_cols = ", ".join(copy_columns)
    insert_cols = ", ".join([*copy_columns, "repo_full_name"])
    op.execute(
        sa.text(
            f"INSERT INTO {table_name} ({insert_cols}) "
            f"SELECT {select_cols}, :repo_full_name FROM {old_name}"
        ).bindparams(repo_full_name=demo_repo)
    )
    op.drop_table(old_name)

    for index_name, index_columns in indexes:
        op.create_index(index_name, table_name, index_columns, unique=False)


def upgrade() -> None:
    demo_repo = _demo_repo_full_name()

    # --- 1) identities / installations / watched_repos (yeni tablolar) ---
    op.create_table(
        "identities",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_user_id", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_user_id", name="uq_identities_provider_user"),
    )
    op.create_index(
        op.f("ix_identities_provider_user_id"), "identities", ["provider_user_id"], unique=False
    )
    op.create_index(op.f("ix_identities_user_id"), "identities", ["user_id"], unique=False)

    op.create_table(
        "installations",
        sa.Column("installation_id", sa.String(length=64), nullable=False),
        sa.Column("account_login", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("installation_id"),
    )
    op.create_index(op.f("ix_installations_user_id"), "installations", ["user_id"], unique=False)

    op.create_table(
        "watched_repos",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("repo_full_name", sa.String(length=255), nullable=False),
        sa.Column("installation_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["installation_id"], ["installations.installation_id"]),
        sa.PrimaryKeyConstraint("user_id", "repo_full_name"),
    )

    # --- 2) users.active_repo_full_name ---
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("active_repo_full_name", sa.String(length=255), nullable=True))

    # --- 3) events: composite PK (id, repo_full_name) ---
    _rebuild_with_tenant_pk(
        table_name="events",
        columns=[
            sa.Column("id", sa.String(length=255), nullable=False),
            sa.Column("repo_full_name", sa.String(length=255), nullable=False),
            sa.Column("type", sa.String(length=20), nullable=False),
            sa.Column("actor", sa.String(length=255), nullable=False),
            sa.Column("branch", sa.String(length=255), nullable=True),
            sa.Column("files", sa.JSON(), nullable=False),
            sa.Column("ts", sa.DateTime(), nullable=False),
            sa.Column("ref", sa.String(length=255), nullable=False),
        ],
        pk_columns=["id", "repo_full_name"],
        indexes=[
            (op.f("ix_events_actor"), ["actor"]),
            (op.f("ix_events_ts"), ["ts"]),
            (op.f("ix_events_repo_full_name"), ["repo_full_name"]),
        ],
        copy_columns=["id", "type", "actor", "branch", "files", "ts", "ref"],
        demo_repo=demo_repo,
    )

    # --- 4) presence: composite PK (handle, repo_full_name) ---
    _rebuild_with_tenant_pk(
        table_name="presence",
        columns=[
            sa.Column("handle", sa.String(length=255), nullable=False),
            sa.Column("repo_full_name", sa.String(length=255), nullable=False),
            sa.Column("task", sa.String(length=50), nullable=True),
            sa.Column("module", sa.String(length=255), nullable=True),
            sa.Column("intent", sa.Text(), nullable=True),
            sa.Column("branch", sa.String(length=255), nullable=True),
            sa.Column("since", sa.DateTime(), nullable=True),
        ],
        pk_columns=["handle", "repo_full_name"],
        indexes=[(op.f("ix_presence_repo_full_name"), ["repo_full_name"])],
        copy_columns=["handle", "task", "module", "intent", "branch", "since"],
        demo_repo=demo_repo,
    )

    # --- 5) task_projection: composite PK (task_id, repo_full_name) ---
    _rebuild_with_tenant_pk(
        table_name="task_projection",
        columns=[
            sa.Column("task_id", sa.String(length=50), nullable=False),
            sa.Column("repo_full_name", sa.String(length=255), nullable=False),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("seed_status", sa.String(length=20), nullable=False, server_default=sa.text("'backlog'")),
            sa.Column("assignee", sa.String(length=255), nullable=True),
            sa.Column("ref", sa.String(length=255), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("last_transition_at", sa.DateTime(), nullable=True),
            sa.Column("last_event_id", sa.String(length=255), nullable=True),
        ],
        pk_columns=["task_id", "repo_full_name"],
        indexes=[
            (op.f("ix_task_projection_status"), ["status"]),
            (op.f("ix_task_projection_repo_full_name"), ["repo_full_name"]),
        ],
        copy_columns=[
            "task_id",
            "title",
            "status",
            "seed_status",
            "assignee",
            "ref",
            "updated_at",
            "last_transition_at",
            "last_event_id",
        ],
        demo_repo=demo_repo,
    )

    # --- 6) task_status_events: composite PK (source_event_id, task_id, repo_full_name) ---
    _rebuild_with_tenant_pk(
        table_name="task_status_events",
        columns=[
            sa.Column("source_event_id", sa.String(length=255), nullable=False),
            sa.Column("task_id", sa.String(length=50), nullable=False),
            sa.Column("repo_full_name", sa.String(length=255), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("ts", sa.DateTime(), nullable=False),
            sa.Column("reason", sa.String(length=255), nullable=True),
            sa.Column("resets", sa.Boolean(), nullable=False, server_default=sa.false()),
        ],
        pk_columns=["source_event_id", "task_id", "repo_full_name"],
        indexes=[
            (op.f("ix_task_status_events_task_id"), ["task_id"]),
            (op.f("ix_task_status_events_ts"), ["ts"]),
            (op.f("ix_task_status_events_repo_full_name"), ["repo_full_name"]),
        ],
        copy_columns=["source_event_id", "task_id", "status", "ts", "reason", "resets"],
        demo_repo=demo_repo,
    )

    # --- 7) vector_index (PostgreSQL-only raw tablo, c4f1d6a2b8e9) ---
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.execute("ALTER TABLE vector_index ADD COLUMN repo_full_name TEXT")
        op.execute(
            sa.text("UPDATE vector_index SET repo_full_name = :repo").bindparams(repo=demo_repo)
        )
        op.execute("ALTER TABLE vector_index ALTER COLUMN repo_full_name SET NOT NULL")
        # PK'yi (id) -> (id, repo_full_name) genişlet — aynı `id`'nin (örn.
        # "task:T-51") iki farklı repoda ayrı vektörü olabilmesi için
        # (bkz. store/models.py composite-PK gerekçesi).
        op.execute("ALTER TABLE vector_index DROP CONSTRAINT vector_index_pkey")
        op.execute("ALTER TABLE vector_index ADD PRIMARY KEY (id, repo_full_name)")


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.execute("ALTER TABLE vector_index DROP CONSTRAINT vector_index_pkey")
        # NOT: downgrade tek-kiracılı öncesi şekle döner — birden fazla
        # kiracının verisi varsa (id) tekil PK'si burada ÇAKIŞABİLİR (aynı id
        # birden çok repoda mevcutsa). Bu, "yıkıcı migration serbest"
        # rebuildable-cache felsefesiyle tutarlı bilinçli bir sınırdır
        # (store/models.py başlık yorumu) — gerçek çok-kiracılı veri üstünde
        # downgrade'in kendisi zaten geri dönülmez bir karardır.
        op.execute("ALTER TABLE vector_index ADD PRIMARY KEY (id)")
        op.execute("ALTER TABLE vector_index ALTER COLUMN repo_full_name DROP NOT NULL")
        op.execute("ALTER TABLE vector_index DROP COLUMN repo_full_name")

    _rebuild_without_tenant_pk(
        table_name="task_status_events",
        columns=[
            sa.Column("source_event_id", sa.String(length=255), nullable=False),
            sa.Column("task_id", sa.String(length=50), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("ts", sa.DateTime(), nullable=False),
            sa.Column("reason", sa.String(length=255), nullable=True),
            sa.Column("resets", sa.Boolean(), nullable=False, server_default=sa.false()),
        ],
        pk_columns=["source_event_id", "task_id"],
        indexes=[
            (op.f("ix_task_status_events_task_id"), ["task_id"]),
            (op.f("ix_task_status_events_ts"), ["ts"]),
        ],
        copy_columns=["source_event_id", "task_id", "status", "ts", "reason", "resets"],
    )

    _rebuild_without_tenant_pk(
        table_name="task_projection",
        columns=[
            sa.Column("task_id", sa.String(length=50), nullable=False),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("seed_status", sa.String(length=20), nullable=False, server_default=sa.text("'backlog'")),
            sa.Column("assignee", sa.String(length=255), nullable=True),
            sa.Column("ref", sa.String(length=255), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("last_transition_at", sa.DateTime(), nullable=True),
            sa.Column("last_event_id", sa.String(length=255), nullable=True),
        ],
        pk_columns=["task_id"],
        indexes=[(op.f("ix_task_projection_status"), ["status"])],
        copy_columns=[
            "task_id",
            "title",
            "status",
            "seed_status",
            "assignee",
            "ref",
            "updated_at",
            "last_transition_at",
            "last_event_id",
        ],
    )

    _rebuild_without_tenant_pk(
        table_name="presence",
        columns=[
            sa.Column("handle", sa.String(length=255), nullable=False),
            sa.Column("task", sa.String(length=50), nullable=True),
            sa.Column("module", sa.String(length=255), nullable=True),
            sa.Column("intent", sa.Text(), nullable=True),
            sa.Column("branch", sa.String(length=255), nullable=True),
            sa.Column("since", sa.DateTime(), nullable=True),
        ],
        pk_columns=["handle"],
        indexes=[],
        copy_columns=["handle", "task", "module", "intent", "branch", "since"],
    )

    _rebuild_without_tenant_pk(
        table_name="events",
        columns=[
            sa.Column("id", sa.String(length=255), nullable=False),
            sa.Column("type", sa.String(length=20), nullable=False),
            sa.Column("actor", sa.String(length=255), nullable=False),
            sa.Column("branch", sa.String(length=255), nullable=True),
            sa.Column("files", sa.JSON(), nullable=False),
            sa.Column("ts", sa.DateTime(), nullable=False),
            sa.Column("ref", sa.String(length=255), nullable=False),
        ],
        pk_columns=["id"],
        indexes=[(op.f("ix_events_actor"), ["actor"]), (op.f("ix_events_ts"), ["ts"])],
        copy_columns=["id", "type", "actor", "branch", "files", "ts", "ref"],
    )

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("active_repo_full_name")

    op.drop_table("watched_repos")
    op.drop_index(op.f("ix_installations_user_id"), table_name="installations")
    op.drop_table("installations")
    op.drop_index(op.f("ix_identities_user_id"), table_name="identities")
    op.drop_index(op.f("ix_identities_provider_user_id"), table_name="identities")
    op.drop_table("identities")


def _rebuild_without_tenant_pk(
    *,
    table_name: str,
    columns: list[sa.Column],
    pk_columns: list[str],
    indexes: list[tuple[str, list[str]]],
    copy_columns: list[str],
) -> None:
    """`_rebuild_with_tenant_pk`'in tersi — `repo_full_name`'i (ve genişletilmiş
    composite PK'yi) DÜŞÜREREK tek-kiracılı öncesi şekle döner. Birden fazla
    repo'nun verisi varsa aynı `id`/`task_id`/`(source_event_id, task_id)`
    çakışıp PK ihlaliyle BAŞARISIZ olur (sessizce veri kaybetmez) — bkz.
    `downgrade()`'in üstteki notu: bu, gerçek çok-kiracılı veri üstünde
    downgrade'in zaten geri dönülmez bir karar olduğunun dürüst ifadesidir."""
    old_name = f"{table_name}_t79_old"
    op.rename_table(table_name, old_name)
    op.create_table(table_name, *columns, sa.PrimaryKeyConstraint(*pk_columns))

    select_cols = ", ".join(copy_columns)
    op.execute(f"INSERT INTO {table_name} ({select_cols}) SELECT {select_cols} FROM {old_name}")
    op.drop_table(old_name)

    for index_name, index_columns in indexes:
        op.create_index(index_name, table_name, index_columns, unique=False)
