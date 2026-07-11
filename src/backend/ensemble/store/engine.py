"""SQLAlchemy engine factory — ENSEMBLE_MODE'a göre SQLite veya PostgreSQL (#41).

Local modda SQLite (repo kökü, gitignored) · hosted modda PostgreSQL DSN.
DB rebuildable cache'tir — yedek gerekmez, yıkıcı migration serbest.
"""

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ensemble.config import Settings


def get_engine(settings: Settings) -> Engine:
    """Settings'e göre SQLAlchemy engine oluştur.

    - SQLite: WAL modu + foreign keys aktif (performans + bütünlük).
    - PostgreSQL: pool boyutu kontrollü.
    """
    url = settings.DATABASE_URL
    is_sqlite = url.startswith("sqlite")

    connect_args = {}
    if is_sqlite:
        # SQLite thread güvenliği — FastAPI'de birden fazla thread kullanılabilir.
        connect_args["check_same_thread"] = False

    engine = create_engine(
        url,
        echo=False,
        connect_args=connect_args,
        pool_pre_ping=not is_sqlite,  # PostgreSQL için bağlantı sağlığı
    )

    # SQLite: WAL modu + foreign keys (her bağlantıda)
    if is_sqlite:

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def get_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Engine'den session factory oluştur."""
    return sessionmaker(bind=engine, expire_on_commit=False)
