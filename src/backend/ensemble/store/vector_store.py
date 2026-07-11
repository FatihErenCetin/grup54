"""VectorStore arayüzü — FAISS (local) / pgvector (hosted) stub (#41).

Gerçek implementasyon #15'in (Semih) işidir. Bu modül yalnızca
arayüz tanımını ve placeholder stub'ı sağlar; #15 merge olunca
gerçek adapter'lar burada (veya ayrı dosyada) yer alacak.

VectorIndexPort zaten ports.py'de Protocol olarak tanımlı — burada
upsert/query imzasıyla uyumlu stub bırakıyoruz.
"""

from ensemble.ports import VectorIndexPort


class StubVectorStore:
    """Placeholder VectorStore — gerçek implementasyon #15'te.

    Tüm operasyonlar no-op; testlerde ve #15 gelene dek stub olarak kullanılır.
    """

    def upsert(self, id: str, vec: list[float], meta: dict) -> None:
        """Vektör ekle/güncelle — stub: no-op."""

    def query(self, vec: list[float], k: int) -> list[tuple[str, float]]:
        """En yakın k vektörü sorgula — stub: boş liste."""
        return []


# Tip kontrolü: StubVectorStore, VectorIndexPort'a uyuyor mu?
_check: VectorIndexPort = StubVectorStore()  # type: ignore[assignment]
