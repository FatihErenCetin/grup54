import re

# Gemini 429'da bize NE KADAR bekleyeceğimizi söyler:
#   {'@type': '.../google.rpc.RetryInfo', 'retryDelay': '30s'}
# ve mesaj metninde de "Please retry in 30.192357358s." olarak geçer.
_RETRY_DELAY_RE = re.compile(
    r"""(?:retryDelay['"]?\s*:\s*['"](?P<yapisal>[\d.]+)s   # RetryInfo alanı
        |[Rr]etry\s+in\s+(?P<duz>[\d.]+)\s*s)               # düz metin cümlesi
    """,
    re.VERBOSE,
)


def sunucunun_bekleme_suresi(metin: str) -> float | None:
    """429 gövdesinden sunucunun DAYATTIĞI bekleme süresini çıkarır.

    Neden gerekli (üretimde ölçüldü, 2026-07-27): ücretsiz katmanda embed
    kotası **dakikada 100 istek**. Sunucu "30 saniye sonra dene" diyor ama
    retry bekleme tavanımız 8 saniyeydi — üç deneme de kota penceresi
    dolmadan harcanıyor ve `make rebuild` düşüyordu. Cevabın İÇİNDE duran
    bilgiyi okumamak, kendi tahminimizle beklemekten kesinlikle daha kötü.

    Ayrıştırılamazsa `None` döner ve çağıran kendi backoff'una düşer —
    burada bir varsayılan UYDURMUYORUZ (yanlış bir sayı, hiç sayı olmamasından
    beterdir: erken uyanıp kotayı tekrar yakar).
    """
    eslesme = _RETRY_DELAY_RE.search(metin)
    if eslesme is None:
        return None
    ham = eslesme.group("yapisal") or eslesme.group("duz")
    try:
        saniye = float(ham)
    except (TypeError, ValueError):
        return None
    # Negatif/absürt değere güvenmiyoruz (bozuk gövde ya da beklenmeyen birim).
    return saniye if 0 < saniye <= 300 else None


class GeminiError(Exception):
    """Gemini entegrasyonu için taban hata sınıfı."""


class GeminiTransientError(GeminiError):
    """Geçici hata — retry edilir (timeout, 429, 5xx, bağlantı kopması).

    `retry_after`: sunucu bir bekleme süresi dayattıysa saniye cinsinden;
    aksi halde `None` (çağıran kendi backoff'unu kullanır).
    """

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class GeminiPermanentError(GeminiError):
    """Kalıcı hata — retry edilmez (400, 401/403, 404, eksik API key)."""
