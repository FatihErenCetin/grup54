"""Projeksiyon deposu — .harness/ + GitHub'dan türetilen hızlı-sorgu cache'i (#41).

Kanonik DEĞİL (çelişkide .harness kazanır; rebuild_projection() ile yeniden kurulur).
users/login tablosu YOK — kapsam dışı (kapsam-sinirlari.md).
"""

from ensemble.store.engine import get_engine, get_session_factory
from ensemble.store.models import Base, EventRow, PresenceRow, TaskProjectionRow
from ensemble.store.rebuild import rebuild_projection

__all__ = [
    "Base",
    "EventRow",
    "PresenceRow",
    "TaskProjectionRow",
    "get_engine",
    "get_session_factory",
    "rebuild_projection",
]
