"""Cakisma precision/recall testleri icin kuratorlu ground-truth korpusu (#26).

Gercek dedektor (#17) henuz yok - bu modul yalnizca etiketli (conflict/no_conflict)
test case'lerini yukler. #17/#18/#28 bu korpusa karsi calisir.
"""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from ensemble.models import NormalizedEvent

_CORPUS_PATH = Path(__file__).parent / "conflict_corpus.jsonl"


class ConflictCase(BaseModel):
    case_id: str
    event_a: NormalizedEvent
    event_b: NormalizedEvent
    overlap: list[str]
    # float = kuratorlu fixture degeri (embeddings'siz geçit testleri icin stand-in);
    # None  = backtest verisi — benzerligi DEDEKTOR hesaplar, dataset'e yazilmaz
    # (veri sizintisi olmasin). Sozlesme: docs/sprint2-kontratlar.md Ek C.
    sim: float | None
    label: Literal["conflict", "no_conflict"]
    note: str


def load_conflict_corpus() -> list[ConflictCase]:
    lines = _CORPUS_PATH.read_text(encoding="utf-8").splitlines()
    return [ConflictCase.model_validate(json.loads(line)) for line in lines if line.strip()]
