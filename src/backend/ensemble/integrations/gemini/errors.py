class GeminiError(Exception):
    """Gemini entegrasyonu için taban hata sınıfı."""


class GeminiTransientError(GeminiError):
    """Geçici hata — retry edilir (timeout, 429, 5xx, bağlantı kopması)."""


class GeminiPermanentError(GeminiError):
    """Kalıcı hata — retry edilmez (400, 401/403, 404, eksik API key)."""
