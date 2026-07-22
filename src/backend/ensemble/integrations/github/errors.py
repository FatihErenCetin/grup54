class GitHubError(Exception):
    """GitHub entegrasyonu icin taban hata sinifi."""


class GitHubConfigError(GitHubError):
    """Eksik/yanlis yerel yapilandirma (APP_ID, pem yolu, installation id, repo owner/name).

    Aga hic cikmadan, adapter/auth somutlastirilirken firlatilir.
    """


class GitHubAuthError(GitHubError):
    """401/403 (kimlik/izin) - kalici, retry edilmez."""


class GitHubNotFoundError(GitHubError):
    """404 - istenen GitHub kaynagi bulunamadi."""


class GitHubTransientError(GitHubError):
    """5xx / baglanti hatasi."""


class GitHubRateLimitError(GitHubTransientError):
    """403 (X-RateLimit-Remaining: 0) veya 429 (secondary rate limit)."""
