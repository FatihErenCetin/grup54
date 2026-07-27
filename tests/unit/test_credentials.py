"""`ensemble.api.credentials` testleri (T-294/D-57) — email normalizasyonu,
parola politikası, argon2id hash/doğrulama, zamanlama savunması.
"""

import time

import pytest

from ensemble.api.credentials import (
    EmailFormatError,
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    PasswordPolicyError,
    hash_password,
    normalize_email,
    validate_email_format,
    validate_password_policy,
    verify_password_or_dummy,
)


# --- normalize_email ---


def test_normalize_email_kucultur_ve_bosluk_kirpar():
    assert normalize_email(" Ali@X.com ") == "ali@x.com"


def test_normalize_email_zaten_normal_degismez():
    assert normalize_email("ali@x.com") == "ali@x.com"


def test_normalize_email_iki_farkli_yazim_ayni_anahtara_dusuyor():
    # #294 brifingi madde 2'nin doğrudan kanıtı: Ali@X.com ile ali@x.com
    # AYNI normalize edilmiş değere düşmeli (aksi halde çift hesap).
    assert normalize_email("Ali@X.com") == normalize_email("ali@x.com")


# --- validate_email_format ---


def test_validate_email_format_gecerli_kabul_eder():
    validate_email_format("ali@x.com")  # exception atmaz


@pytest.mark.parametrize("bozuk", ["", "aliatx.com", "ali@", "ali @x.com", "ali@xcom"])
def test_validate_email_format_bozugu_reddeder(bozuk):
    with pytest.raises(EmailFormatError):
        validate_email_format(bozuk)


# --- validate_password_policy ---


def test_validate_password_policy_asgari_uzunluk_altinda_reddeder():
    with pytest.raises(PasswordPolicyError):
        validate_password_policy("a" * (MIN_PASSWORD_LENGTH - 1))


def test_validate_password_policy_asgari_uzunluk_kabul_eder():
    validate_password_policy("a" * MIN_PASSWORD_LENGTH)  # exception atmaz


def test_validate_password_policy_azami_uzunluk_ustunde_reddeder():
    with pytest.raises(PasswordPolicyError):
        validate_password_policy("a" * (MAX_PASSWORD_LENGTH + 1))


def test_validate_password_policy_azami_uzunlugu_kabul_eder():
    validate_password_policy("a" * MAX_PASSWORD_LENGTH)  # exception atmaz


# --- hash_password / verify_password_or_dummy ---


def test_hash_password_dogru_parolayla_dogrulanir():
    password_hash = hash_password("dogru-parola-123")
    assert verify_password_or_dummy(password_hash, "dogru-parola-123") is True


def test_hash_password_yanlis_parolayla_reddedilir():
    password_hash = hash_password("dogru-parola-123")
    assert verify_password_or_dummy(password_hash, "yanlis-parola-456") is False


def test_hash_password_ayni_parola_farkli_hash_uretir():
    # argon2id her çağrıda rastgele tuz kullanır — iki hash BİT-BİT eşit
    # olmamalı (rainbow-table/hash-karşılaştırma saldırısına karşı).
    h1 = hash_password("ayni-parola")
    h2 = hash_password("ayni-parola")
    assert h1 != h2
    assert verify_password_or_dummy(h1, "ayni-parola") is True
    assert verify_password_or_dummy(h2, "ayni-parola") is True


def test_verify_password_or_dummy_hash_none_ise_false_doner():
    # Kullanıcı yok (ya da yalnız-GitHub hesap, password_hash NULL) — GERÇEK
    # bir eşleşme asla dönmemeli, ne parola girilirse girilsin.
    assert verify_password_or_dummy(None, "herhangi-bir-parola") is False


def test_verify_password_or_dummy_bozuk_hash_500e_sizmadan_false_doner():
    assert verify_password_or_dummy("bozuk-hash-degeri", "parola") is False


def test_verify_password_or_dummy_hash_none_iken_de_argon2_isini_yapar():
    """#294 brifingi madde 6 — zamanlama/kullanıcı-sayımı savunmasının temel
    dayanağı: `password_hash=None` dalı da GERÇEK bir argon2 doğrulaması
    çalıştırmalı (yalnızca `return False` ile erken çıkmamalı), aksi halde
    "kullanıcı yok" dalı ölçülebilir şekilde daha hızlı olur.

    Doğrudan iki JITTER'lı ortalama karşılaştırmak (gerçek bir zamanlama testi)
    CI'da gürültülü/kırılgan olurdu — bunun yerine DAVRANIŞSAL bir kanıt
    kullanılır: her iki dal da somut, ölçülebilir bir süre (argon2 hash'leme
    mertebesinde, birkaç ms) tüketiyor mu? `None` dalı "anında" (mikrosaniye
    mertebesinde) dönerse, iş yapmadığının kanıtıdır — bu asıl regresyonu
    (erken `return False`) yakalar; ortam gürültüsüne karşı ise dayanıklıdır.
    """
    real_hash = hash_password("gercek-parola-1234")

    start = time.perf_counter()
    verify_password_or_dummy(real_hash, "yanlis-tahmin")
    real_branch_s = time.perf_counter() - start

    start = time.perf_counter()
    verify_password_or_dummy(None, "yanlis-tahmin")
    none_branch_s = time.perf_counter() - start

    # İkisi de argon2'nin GERÇEK maliyetini (tipik olarak >= birkaç ms)
    # taşımalı — "anında dönen" bir dal (örn. <0.5ms) iş yapmadığını ele verir.
    assert real_branch_s > 0.0005, f"gerçek dal beklenenden hızlı: {real_branch_s}s"
    assert none_branch_s > 0.0005, f"None dalı beklenenden hızlı (argon2 atlanmış olabilir): {none_branch_s}s"
