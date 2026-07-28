from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable, Literal

from sqlalchemy.orm import Session

from ensemble.models import BoardCard
from ensemble.store.models import DEFAULT_REPO_FULL_NAME, TaskProjectionRow


@dataclass(frozen=True)
class BoardResult:
    """`get_board()` çıktısı — kartlar + board-genelinde provenance (İş 4, #33 B1 eki).

    `BoardCard` (S3 B1 🔒 kontratı) DEĞİŞMEZ; provenance yalnız bu zarfta taşınır.
    """

    cards: list[BoardCard]
    last_transition_at: datetime | None
    source: Literal["seed", "ingest"]


def compute_board_provenance(rows: Iterable[object]) -> tuple[datetime | None, Literal["seed", "ingest"]]:
    """Satırlardaki (İş 2'nin ekleyeceği) `last_transition_at` alanından board-genelinde
    provenance türetir — SAF fonksiyon, DB'ye dokunmaz (ayrık test edilebilir).

    İş 2 henüz merge olmadıysa `TaskProjectionRow`'da `last_transition_at` kolonu
    YOKTUR; `getattr(..., None)` bunu sessizce yutmaz, GERÇEĞİ yansıtır: hiçbir
    satırda geçiş yoksa board fiilen tamamen tohumdan geliyordur -> "seed" DOĞRU
    cevaptır (fail-open değil, dürüst varsayılan).

    En az bir satırda geçiş varsa `source="ingest"` ve `last_transition_at` =
    o geçişlerin EN SONUNCUSU (board'un en taze bilgisi).
    """
    timestamps = [ts for row in rows if (ts := getattr(row, "last_transition_at", None)) is not None]
    if not timestamps:
        return None, "seed"
    return max(timestamps), "ingest"


class BoardService:
    """`repo_full_name` (T-79, çok-kiracılık): her kiracı KENDİ `BoardService`
    örneğine sahiptir (bkz. ensemble/tenancy.py) — bu port'un imzası
    (`get_cards`/`get_board`) DEĞİŞMEDİ, yalnızca constructor'a kiracı
    bağlanıyor (GitHubAdapter'ın owner/repo'yu constructor'da bağlamasıyla
    aynı desen)."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        repo_full_name: str = DEFAULT_REPO_FULL_NAME,
    ):
        self.session_factory = session_factory
        self.repo_full_name = repo_full_name

    def get_cards(self) -> list[BoardCard]:
        with self.session_factory() as session:
            rows = (
                session.query(TaskProjectionRow)
                .filter_by(repo_full_name=self.repo_full_name)
                .all()
            )
            return [row.to_board_card() for row in rows]

    def get_board(self) -> BoardResult:
        """`get_cards()` + board-genelinde provenance (last_transition_at/source).

        Ayrı bir metod — `get_cards()` imzası/davranışı DEĞİŞMEDİ (mevcut
        çağıranlar kırılmaz, kabul kriteri).
        """
        with self.session_factory() as session:
            rows = (
                session.query(TaskProjectionRow)
                .filter_by(repo_full_name=self.repo_full_name)
                .all()
            )
            cards = [row.to_board_card() for row in rows]
            last_transition_at, source = compute_board_provenance(rows)
            return BoardResult(cards=cards, last_transition_at=last_transition_at, source=source)
