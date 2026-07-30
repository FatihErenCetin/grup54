"""`GitHubPort`in YAZMA yuzeyinin gercek REST implementasyonu (#339).

Neden AYRI dosya (adapter.py'nin icine gomulmedi): bu, urunun dis dunyaya
acilan ILK yazma yolu. Ayri bir dosyada durmasi iki sey saglar —
(1) "hangi kod GitHub'a YAZABILIR" sorusunun cevabi tek bir dosyaya bakarak
verilebilir (audit yuzeyi kucuk), (2) `GitHubAdapter` 270 satirlik salt-okunur
gecmisiyle karismaz.

`GitHubAdapter` bunu miras alir (`class GitHubAdapter(GitHubWriteMixin)`) —
mixin `self._owner` / `self._repo` / `self._client` uclusunu bekler, ki bunlar
`GitHubAdapter.__init__` tarafindan zaten kurulur.

YORUM UCU NOTU: PR "konusma" yorumlari GitHub'da **issues** ucundan yazilir
(`POST /repos/{o}/{r}/issues/{n}/comments`). `/pulls/{n}/comments` BASKA bir
seydir (satir-ici review yorumu, `commit_id`+`path`+`line` ister ve diff'e
capalanir). Yanlis ucu secmek, testler yesilken canlida 422 demek olurdu.
"""

from typing import Any

from ensemble.integrations.github.errors import GitHubError

# Bir PR'in yorumlari kac sayfa (100'luk) taranir. Idempotency BU taramaya
# dayaniyor: isaretimiz taranmayan bir sayfada kalirsa AYNI tespit icin IKINCI
# yorum yazilir. Bu yuzden sinir asilirsa sessizce kirpmiyoruz — ISTISNA
# firlatiyoruz (asagida), yani "tarayamadim" asla "yorum yok" diye okunmaz.
_MAX_YORUM_SAYFASI = 20
_SAYFA_BOYU = 100


class GitHubWriteMixin:
    """Yazma yolu — `pull_request_open` · `list_pull_request_comment_bodies` ·
    `create_pull_request_comment` (bkz. `ensemble.ports.GitHubPort`)."""

    _owner: str
    _repo: str
    _client: Any

    def pull_request_open(self, number: int) -> bool:
        """PR gercekten ACIK mi (kapali/merge edilmis PR'a yazilmaz).

        `state == "open"` TEK BASINA yeterli degil mi? Evet, GitHub merge
        edilmis PR'i `closed` yapar. Yine de `merged`i AYRICA kontrol
        ediyoruz: alan varsa ve `True` ise, `state` ne derse desin yazmayiz —
        iki bagimsiz sinyalin ikisi de "acik" demedikce yazma yapilmaz.

        Govde okunamazsa (`None`) `False` DONMEZ: `GitHubError` firlatir.
        "Kapali" bir OLGU, "durumu ogrenemedim" ise olgunun YOKLUGU; ikincisini
        birincisine cevirmek, cagiranin `pr_kapali` diye YANLIS bir sonuc
        raporlamasina yol acardi (#252 dersi).
        """
        data = self._client.get(
            f"/repos/{self._owner}/{self._repo}/pulls/{number}",
            cache_key=f"write:pull:{number}",
        )
        if not isinstance(data, dict):
            raise GitHubError(
                f"PR #{number} durumu okunamadi (govde: {type(data).__name__}) — "
                "yazma guvenli degil"
            )
        if data.get("merged") is True or data.get("merged_at"):
            return False
        return str(data.get("state") or "").lower() == "open"

    def list_pull_request_comment_bodies(self, number: int) -> list[str]:
        """PR'in mevcut konusma yorumlarinin GOVDELERI (idempotency taramasi).

        Sayfalama ZORUNLU ve `cache_key` sayfa numarasini ICERIR — ayni ETag
        tuzagi burada da gecerli (bkz. adapter.py `_sayfali` docstring'i):
        sayfa numarasi anahtara girmezse 2. sayfa 1. sayfanin govdesini replay
        eder, ayni 100 yorum tekrar gelir ve isaretimiz asla bulunmaz →
        her turda YENI bir yorum yazilir.
        """
        bodies: list[str] = []
        sayfa = 1
        while sayfa <= _MAX_YORUM_SAYFASI:
            govde = self._client.get(
                f"/repos/{self._owner}/{self._repo}/issues/{number}/comments",
                params={"per_page": _SAYFA_BOYU, "page": sayfa},
                cache_key=f"write:pr_comments:{number}:p{sayfa}",
            )
            if not govde:
                return bodies
            if not isinstance(govde, list):
                raise GitHubError(
                    f"PR #{number} yorum listesi beklenen bicimde degil "
                    f"({type(govde).__name__})"
                )
            bodies.extend(str(item.get("body") or "") for item in govde)
            if len(govde) < _SAYFA_BOYU:
                return bodies
            sayfa += 1

        raise GitHubError(
            f"PR #{number} yorumlari {_MAX_YORUM_SAYFASI} sayfada bitmedi — "
            "idempotency taramasi TAMAMLANAMADI, yazma reddedildi"
        )

    def create_pull_request_comment(self, number: int, body: str) -> str:
        """PR'a konusma yorumu yazar; yorumun URL'sini doner.

        Hata YUTULMAZ: 403 (izin yok) / 404 / 5xx `GitHubRestClient.post`
        icinde istisnaya cevrilir ve buradan YUKARI yayilir.

        Yanit govdesinde `html_url` yoksa ISTISNA FIRLATILMAZ — yazma
        GERCEKTEN oldu (2xx), eksik olan yalnizca kozmetik bir referans;
        burada patlamak "basarili yazmayi basarisiz raporlamak" olurdu (ters
        yonde ama yine yanlis bir rapor). Yerine dogrulanabilir bir referans
        (`pr#<n>`) doneriz.
        """
        data = self._client.post(
            f"/repos/{self._owner}/{self._repo}/issues/{number}/comments",
            json={"body": body},
        )
        if isinstance(data, dict) and data.get("html_url"):
            return str(data["html_url"])
        return f"pr#{number}"
