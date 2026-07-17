"""Projeksiyon deposu — .harness/ + GitHub'dan türetilen hızlı-sorgu cache'i (#41).

Kanonik DEĞİL (çelişkide .harness kazanır; rebuild_projection() ile yeniden kurulur).
users/login tablosu YOK — kapsam dışı (kapsam-sinirlari.md).
"""

from ensemble.store.engine import get_engine, get_session_factory
from ensemble.store.models import Base, EventRow, PresenceRow, TaskProjectionRow
from ensemble.store.rebuild import rebuild_projection
from ensemble.store.vector_store import (
    FaissVectorIndex,
    LocalVectorIndex,
    PgVectorIndex,
    build_vector_index,
)

__all__ = [
    "Base",
    "EventRow",
    "FaissVectorIndex",
    "LocalVectorIndex",
    "PgVectorIndex",
    "PresenceRow",
    "TaskProjectionRow",
    "build_vector_index",
    "get_engine",
    "get_session_factory",
    "rebuild_projection",
]
