class GroqError(Exception):
    """Groq entegrasyonu icin taban hata sinifi."""


class GroqTransientError(GroqError):
    """Gecici hata: timeout, baglanti, 429 veya 5xx."""


class GroqPermanentError(GroqError):
    """Kalici hata: hatali istek/model, gecersiz anahtar veya bozuk yanit."""
