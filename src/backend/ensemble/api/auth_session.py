"""Oturum çerezi imzalama (#79 daraltılmış dilim — GitHub App kullanıcı girişi;
T-294/D-57 ile email+parola üyeliğine GENİŞLETİLDİ).

`itsdangerous` YERİNE stdlib `hmac` — `webhook.py::verify_signature` ile AYNI
disiplin (`GITHUB_WEBHOOK_SECRET` yerine `AUTH_SESSION_SECRET`), yeni bir
bağımlılık eklemeden mevcut deseni tekrar kullanır.

Format: `base64url_nopad(payload_json) + "." + hmac_sha256(payload_bytes).hexdigest()`.
Payload ASLA GitHub access token/parola TAŞIMAZ — yalnız kimlik GÖRÜNÜMÜ:
`{"handle": str|None, "avatar_url": str|None, "sub"?: str, "email"?: str}`.

GERİYE UYUMLULUK (T-294 kritik gereksinim): `sub`/`email` alanları YALNIZCA
verildiklerinde payload'a eklenir (`None` iseler payload'da hiç GÖRÜNMEZLER).
Bu yüzden `sign_session(secret, handle=..., avatar_url=...)` (GitHub akışının
BUGÜNKÜ tek çağrı biçimi) BİT-BİT AYNI `{"handle":.., "avatar_url":..}`
gövdesini üretmeye devam eder — bugüne kadar verilmiş çerezler YARIN da
GEÇERLİ kalır (kod değişmeden önce imzalanmış bir çerez, kod değiştikten
SONRA da aynı şekilde doğrulanır). Email hesapları `handle=None` ile
imzalanır (GitHub handle'ları yok) ve kimliklerini `sub` (users.id) +
`email` alanlarıyla taşır — bkz. `verify_session`'ın gözden geçirilmiş
geçerlilik kapısı (ne `handle` NE `sub` varsa reddedilir; İKİSİNDEN biri
yeterlidir, ikisi BİRDEN gerekmez).

Base64 dolgusu (`=`) BİLEREK atılır (JWT'nin de yaptığı gibi, RFC 7515 §2) —
Python'un `http.cookies` modülü (Starlette `set_cookie` bunun üzerine kurulu)
değeri `=` gördüğünde OTOMATİK OLARAK tırnak içine alır (`_LegalChars`'ta yok);
tırnaklı değerin istemci tarafında doğru saklanıp saklanmadığı istemciye göre
değişir (ölçüldü: httpx'in test istemcisi tırnakları KALDIRMADAN saklıyor,
bu da geri gönderilen değeri imza doğrulamasını KIRACAK şekilde bozuyor).
Dolgusuz base64 bu belirsizliği tamamen ORTADAN KALDIRIR — değerde `=` hiç
oluşmaz, hangi istemci/kütüphane olursa olsun quoting devreye girmez.
"""

import base64
import hashlib
import hmac
import json

# Çerez adları — router (routers/auth.py) ve bu modül TEK kaynaktan okur,
# adlar iki yerde tekrarlanıp sessizce kaymasın diye burada sabitlenir.
SESSION_COOKIE_NAME = "ensemble_session"
STATE_COOKIE_NAME = "ensemble_oauth_state"


class SessionSignatureError(Exception):
    """Çerez eksik/bozuk/imza uyuşmuyor — çağıran bunu 401'e çevirir."""


def _signature(secret: str, payload_b64: bytes) -> str:
    return hmac.new(secret.encode(), payload_b64, hashlib.sha256).hexdigest()


def _b64_encode_nopad(data: bytes) -> bytes:
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def _b64_decode_nopad(data: bytes) -> bytes:
    padding = b"=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def sign_session(
    secret: str,
    *,
    handle: str | None = None,
    avatar_url: str | None = None,
    sub: str | None = None,
    email: str | None = None,
) -> str:
    """`handle`/`avatar_url` HER ZAMAN gövdede (None bile olsalar) — GitHub
    akışının bugünkü çağrı biçimiyle (`handle=<str>, avatar_url=<str|None>`)
    BİT-BİT AYNI şekli üretmeye devam eder (geriye uyumluluk). `sub`/`email`
    yalnız verildiklerinde (email akışı) eklenir — GitHub akışı bunları hiç
    geçmediği için payload'ında hiç GÖRÜNMEZLER."""
    payload: dict[str, object] = {"handle": handle, "avatar_url": avatar_url}
    if sub is not None:
        payload["sub"] = sub
    if email is not None:
        payload["email"] = email
    payload_json = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload_b64 = _b64_encode_nopad(payload_json)
    return f"{payload_b64.decode('ascii')}.{_signature(secret, payload_b64)}"


def verify_session(secret: str, cookie_value: str) -> dict:
    """Çözer + imzayı doğrular; herhangi bir adımda başarısızlık
    `SessionSignatureError` fırlatır (çağıran tek bir yerde 401'e çevirir)."""
    try:
        payload_b64_str, signature = cookie_value.rsplit(".", 1)
    except ValueError as exc:
        raise SessionSignatureError("çerez biçimi geçersiz (ayraç yok)") from exc

    try:
        payload_b64 = payload_b64_str.encode("ascii")
    except UnicodeEncodeError as exc:
        raise SessionSignatureError("çerez gövdesi ASCII değil") from exc
    expected = _signature(secret, payload_b64)
    # timing-safe karşılaştırma — webhook.py::verify_signature ile aynı desen.
    # ASCII-dışı/bozuk girdide compare_digest TypeError atabilir; fail-closed
    # aynı SessionSignatureError'a çevrilir (500'e sızmaz, #62 dersi).
    try:
        signatures_match = hmac.compare_digest(expected, signature)
    except TypeError as exc:
        raise SessionSignatureError("imza karşılaştırılamadı") from exc
    if not signatures_match:
        raise SessionSignatureError("çerez imzası uyuşmuyor")

    try:
        payload = json.loads(_b64_decode_nopad(payload_b64))
    except (ValueError, UnicodeDecodeError) as exc:
        raise SessionSignatureError("çerez gövdesi çözülemedi") from exc

    # T-294: `handle` artık İSTEĞE BAĞLI (email hesaplarının GitHub handle'ı
    # yok) — kapı `handle` VEYA `sub`'dan en az biri GERÇEKTEN dolu (truthy)
    # mu diye bakar. `.get()` + truthiness BİLEREK "anahtar var mı" (eski
    # kod) yerine kullanılıyor: `sign_session` artık HER token'a `handle`
    # anahtarını (değeri None olsa bile) ekliyor — salt anahtar-varlığı kapısı
    # email token'ları da (handle=None) sessizce "geçerli" sayardı, kapıyı
    # anlamsızlaştırırdı. Eski/bozuk gövdeler (`{"no_handle": "x"}` gibi, ne
    # handle ne sub) yine reddedilir.
    if not isinstance(payload, dict) or not (payload.get("handle") or payload.get("sub")):
        raise SessionSignatureError("çerez gövdesinde ne handle ne sub var")
    return payload
