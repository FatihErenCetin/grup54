class OllamaError(Exception):
    """Ollama entegrasyonu icin taban hata sinifi."""


class OllamaTransientError(OllamaError):
    """Gecici hata: timeout, baglanti, 429 veya 5xx."""


class OllamaPermanentError(OllamaError):
    """Kalici hata: hatali istek/model veya gecersiz yanit."""
