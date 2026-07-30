"""#343 — Vercel preview origin'leri CORS'tan geçmeli, yabancı origin'ler GEÇMEMELİ.

Ölçüm (30 Tem, canlı): preview sayfası açılıyordu ama `/health` ve `/events`
CORS'a takılıyordu; Semih #322'yi bu yüzden görsel olarak doğrulayamadı ve
ikinci kez changes-requested verdi. Dört tasarım PR'ı review'da tıkandı.

Bu testler config doğrulamasını DEĞİL, gerçek middleware davranışını ölçer:
gerçek bir istek + `Origin` başlığı + dönen `access-control-allow-origin`.
"""

from fastapi.testclient import TestClient

import pytest

from ensemble.app import create_app
from ensemble.config import Settings

_PREVIEW_DESEN = r"^https://grup54-git-[a-z0-9-]+-fatihs-projects-7334d9e4\.vercel\.app$"
_PREVIEW = "https://grup54-git-t-319-ask-activity-fatihs-projects-7334d9e4.vercel.app"
_PROD = "https://recommend2me.com"


def _istemci(*, regex: str | None) -> TestClient:
    ayar = Settings(
        _env_file=None,
        CORS_ORIGINS=_PROD,
        CORS_PREVIEW_ORIGIN_REGEX=regex,
    )
    return TestClient(create_app(settings=ayar))


def _izin_verilen(client: TestClient, origin: str) -> str | None:
    yanit = client.get("/health", headers={"Origin": origin})
    return yanit.headers.get("access-control-allow-origin")


def test_preview_origini_regex_ACIKKEN_gecer():
    """MUTASYON KİLİDİ: `allow_origin_regex` bağlantısını app.py'den kaldır →
    bu test düşer ve Semih'in bildirdiği hata geri gelir."""
    with _istemci(regex=_PREVIEW_DESEN) as c:
        assert _izin_verilen(c, _PREVIEW) == _PREVIEW


def test_preview_origini_regex_KAPALIYKEN_gecmez():
    """Fail-closed: ayar verilmemişse davranış AYNEN eskisi gibi kalır
    (totoloji panzehiri — yukarıdaki testin 'geçti'si regex'ten mi geliyor,
    yoksa kurulum zaten her şeye izin mi veriyor?)."""
    with _istemci(regex=None) as c:
        assert _izin_verilen(c, _PREVIEW) is None


def test_production_origini_her_iki_kurulumda_da_calisir():
    """Regex eklemek mevcut allowlist'i BOZMAMALI."""
    for regex in (None, _PREVIEW_DESEN):
        with _istemci(regex=regex) as c:
            assert _izin_verilen(c, _PROD) == _PROD


@pytest.mark.parametrize(
    "yabanci",
    [
        "https://kotucul.example",
        # Desenimizi SONUNA ekleyen klasik kandirma denemesi — capa (`$`) bunu
        # kapatir; capasiz desen `re.match` ile ESLESIRDI.
        "https://kotucul.example/grup54-git-x-fatihs-projects-7334d9e4.vercel.app",
        # Bizim projemiz DEGIL, baska bir Vercel projesi
        "https://grup54-git-x-baskasinin-projesi.vercel.app",
        # Alt alan adi enjeksiyonu
        "https://grup54-git-x-fatihs-projects-7334d9e4.vercel.app.kotucul.example",
    ],
)
def test_YABANCI_originler_regex_acikken_de_REDDEDILIR(yabanci: str):
    """MUTASYON KİLİDİ: deseni `^.*$` yap → config açılışta reddeder; çapayı
    kaldır → bu testlerden en az biri düşer."""
    with _istemci(regex=_PREVIEW_DESEN) as c:
        assert _izin_verilen(c, yabanci) is None, f"{yabanci} GECMEMELI"


def test_capasiz_desen_ACILISTA_reddedilir():
    """Çapasız desen `re.match` ile beklenenden geniş eşleşir — açılışta
    reddedilir, sessizce kabul edilip üretimde sürpriz yapmaz."""
    with pytest.raises(Exception, match="çapa|başlayıp|'\\^'"):
        Settings(_env_file=None, CORS_PREVIEW_ORIGIN_REGEX="https://.*vercel.app")
