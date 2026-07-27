"""Oturum çerezi imzalama (#79 daraltılmış dilim) testleri — api/auth_session.py.

Round-trip + kurcalama tespiti (bit çevirme, imza değiştirme, ayraç eksikliği,
ASCII-dışı gövde, `handle` eksik gövde) — hepsi `SessionSignatureError`'a
düşmeli, hiçbiri istisnasız sessizce geçmemeli.
"""

import pytest

from ensemble.api.auth_session import SessionSignatureError, sign_session, verify_session

_SECRET = "test-session-secret"


def test_round_trip_ayni_veriyi_dondurur():
    token = sign_session(_SECRET, handle="esma6", avatar_url="https://example.com/a.png")
    payload = verify_session(_SECRET, token)
    assert payload == {"handle": "esma6", "avatar_url": "https://example.com/a.png"}


def test_avatar_url_none_de_calisir():
    token = sign_session(_SECRET, handle="fatih", avatar_url=None)
    payload = verify_session(_SECRET, token)
    assert payload == {"handle": "fatih", "avatar_url": None}


def test_yanlis_secret_reddedilir():
    token = sign_session(_SECRET, handle="esma6", avatar_url=None)
    with pytest.raises(SessionSignatureError):
        verify_session("baska-bir-secret", token)


def test_govde_kurcalanirsa_reddedilir():
    """Payload'ı değiştirip imzayı ESKİ bırakmak (klasik JWT 'alg=none' tarzı
    saldırı) imza uyuşmazlığına düşmeli."""
    token = sign_session(_SECRET, handle="esma6", avatar_url=None)
    payload_b64, signature = token.rsplit(".", 1)
    tampered_payload = payload_b64[:-1] + ("A" if payload_b64[-1] != "A" else "B")
    with pytest.raises(SessionSignatureError):
        verify_session(_SECRET, f"{tampered_payload}.{signature}")


def test_imza_kurcalanirsa_reddedilir():
    token = sign_session(_SECRET, handle="esma6", avatar_url=None)
    payload_b64, signature = token.rsplit(".", 1)
    tampered_sig = "0" * len(signature)
    with pytest.raises(SessionSignatureError):
        verify_session(_SECRET, f"{payload_b64}.{tampered_sig}")


def test_ayrac_yoksa_reddedilir():
    with pytest.raises(SessionSignatureError):
        verify_session(_SECRET, "ayracsiz-tek-parca")


def test_ascii_disi_govde_401_e_esdeger_hata_verir_500_degil():
    """webhook.py::verify_signature'daki 'ASCII-dışı 500'e sızmasın' dersinin
    (#62) bu modüldeki ikizi — compare_digest/encode TypeError'ı yutulur."""
    with pytest.raises(SessionSignatureError):
        verify_session(_SECRET, "\xe9" * 10 + "." + "0" * 64)


def test_bozuk_base64_reddedilir():
    with pytest.raises(SessionSignatureError):
        verify_session(_SECRET, "!!!not-base64!!!.aabbcc")


def test_handle_eksik_govde_reddedilir():
    """İmza doğru olsa bile şemayla uyuşmayan (handle'sız) gövde reddedilmeli —
    imzalamayı BU modül yaptığı sürece pratikte oluşmaz ama savunma amaçlı."""
    import base64
    import hashlib
    import hmac
    import json

    payload = json.dumps({"no_handle": "x"}).encode()
    payload_b64 = base64.urlsafe_b64encode(payload)
    sig = hmac.new(_SECRET.encode(), payload_b64, hashlib.sha256).hexdigest()
    with pytest.raises(SessionSignatureError):
        verify_session(_SECRET, f"{payload_b64.decode()}.{sig}")
