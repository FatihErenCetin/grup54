"""Alembic migration `3a2ba7afdced` (events.actor_verified, #296/T-296) —
GERÇEK bir SQLite dosyasına karşı upgrade+downgrade doğrulaması.

Bilinçli tasarım: ayrı bir alt-süreçte (`python -m alembic`) çalıştırılır,
`Settings.get_settings()` process-genelinde `lru_cache`'li olduğu için AYNI
pytest süreci içinde `DATABASE_URL` env değişkeniyle oynamak diğer testlerin
(veya sonraki testlerin) cache'ini kirletebilirdi — alt-süreç izolasyonu bunu
sıfırlar (bkz. ensemble/config.py::get_settings).

Bu repoda daha önce bir migration fork'u yaşandığı için (bkz. 9aa33a394b2d
docstring'i) `alembic heads` TEK head vermeli - bu da ayrıca doğrulanır.
"""

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).parent.parent.parent / "src" / "backend"


def _run_alembic(*args: str, db_path: Path) -> subprocess.CompletedProcess:
    import os

    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}"}
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", *args],
        cwd=_BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.fixture(scope="module")
def _tek_head_dogrulandi():
    """Bu modüldeki TÜM testlerden önce bir kere: `alembic heads` tek satır
    döner mi? (migration fork regresyonu — #79 döneminde yaşandı)."""
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "heads"],
        cwd=_BACKEND_DIR,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    heads = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(heads) == 1, f"BEKLENMEYEN migration fork'u - birden fazla head: {heads}"
    return heads[0]


def test_upgrade_head_temiz_calisir(tmp_path, _tek_head_dogrulandi):
    db_path = tmp_path / "migration-actor-verified.db"
    result = _run_alembic("upgrade", "head", db_path=db_path)
    assert result.returncode == 0, result.stderr

    conn = sqlite3.connect(db_path)
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
        assert "actor_verified" in cols
    finally:
        conn.close()


def test_mevcut_satirlar_dogrulanmis_a_backfill_edilir(tmp_path, _tek_head_dogrulandi):
    """PO kararı (#296 'kısa vadeli temizlik'): mevcut (eşleşmeyen dahil)
    satırlara dokunulmaz, hepsi güvenli varsayılana ('doğrulanmış') düşer -
    geçmiş yeniden YORUMLANMAZ."""
    db_path = tmp_path / "migration-backfill.db"

    # Son migration'dan BİR ÖNCEKİ duruma kadar yükselt, elle bir satır ekle,
    # SONRA son migration'ı uygula - backfill'i gerçek bir "mevcut satır"
    # üzerinde ölçmek için (boş tablo backfill'i test etmez).
    pre = _run_alembic("upgrade", "a1f7c9d4e2b6", db_path=db_path)
    assert pre.returncode == 0, pre.stderr

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO events (id, repo_full_name, type, actor, branch, files, ts, ref) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "commit:preexisting",
                "default/repo",
                "commit",
                "Merge Simulation",
                None,
                "[]",
                "2026-07-01 00:00:00",
                "abc",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    head = _run_alembic("upgrade", "head", db_path=db_path)
    assert head.returncode == 0, head.stderr

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT actor, actor_verified FROM events WHERE id = ?", ("commit:preexisting",)
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    actor, actor_verified = row
    assert actor == "Merge Simulation"
    assert actor_verified == 1  # SQLite boolean -> 1/0; backfill "doğrulanmış"


def test_downgrade_kolonu_temiz_kaldirir(tmp_path, _tek_head_dogrulandi):
    db_path = tmp_path / "migration-downgrade.db"
    up = _run_alembic("upgrade", "head", db_path=db_path)
    assert up.returncode == 0, up.stderr

    # `-1` DEĞİL, hedef revizyon ADIYLA geri sarılır. `-1` "head'in bir
    # öncesi" demektir ve bu testin doğrulamak istediği migration'ın HEAD
    # OLDUĞUNU varsayar — zincire yeni bir migration eklenince (#355,
    # e5b8d2c71a09) test sessizce BAŞKA bir migration'ı sınamaya başlar.
    # `3a2ba7afdced` actor_verified'ı ekleyen revizyon; TAM bir öncesine
    # (`a1f7c9d4e2b6`) inmek yalnız onu geri alır. Daha geriye inmek
    # çok-kiracılık migration'ını da geri sarar ve composite PK iddiası
    # (aşağıda) yanlış sebeple kırılırdı.
    down = _run_alembic("downgrade", "a1f7c9d4e2b6", db_path=db_path)
    assert down.returncode == 0, down.stderr

    conn = sqlite3.connect(db_path)
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
        # PK/indeksler de sağ kalmalı (batch_alter_table tabloyu yeniden
        # kurar) - composite PK (id, repo_full_name) hâlâ orada mı?
        pk_cols = {row[1] for row in conn.execute("PRAGMA table_info(events)") if row[5] > 0}
    finally:
        conn.close()
    assert "actor_verified" not in cols
    assert pk_cols == {"id", "repo_full_name"}
