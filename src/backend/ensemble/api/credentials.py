"""E-posta + parola üyelik ilkelleri (T-294/D-57) — GitHub OAuth'un YANINDA,
onun yerine değil (bkz. `.harness/decisions/D-57-email-parola-uyeligi.md`).

Üç sorumluluk TEK bu modülde toplanır — hepsi TEK yerde olmalı, aksi halde
sessizce kayan bir davranış farkı çıkar:

1. **E-posta normalizasyonu** (`normalize_email`) — kayıt VE giriş yolunun
   İKİSİ de bunu çağırmak ZORUNDA. İki farklı normalize (örn. biri yalnızca
   `.lower()`, diğeri `.strip().lower()`) `Ali@X.com` ile `ali@x.com`'un
   FARKLI benzersizlik anahtarına düşmesine, yani sessizce çift hesaba yol
   açar (#294 brifingi, madde 2).
2. **Parola politikası** (`validate_password_policy`) — tek yerde, TR +
   eyleme dönük mesajla. Üst sınır (128) BİLİNÇLİ: argon2id uzun girdide
   doğrusal yavaşlar, sınırsız uzunluk bir DoS yüzeyi açar.
3. **Hash + doğrulama** (`hash_password`, `verify_password_or_dummy`) —
   argon2id (argon2-cffi). **bcrypt YERİNE**: bcrypt'in 72-bayt sessiz
   kırpma tuzağı var (72. bayttan sonrası hash'e hiç girmez; iki farklı uzun
   parola aynı hash'e düşebilir) — argon2id bu sınırı taşımaz.

Zamanlama/numaralandırma savunması (#294 brifingi, madde 6):
`verify_password_or_dummy` çağırana e-posta VAR MI bilgisini SIZDIRMAZ —
kullanıcı bulunamadığında bile SABİT bir sahte hash'e karşı GERÇEK bir
argon2 doğrulaması çalıştırılır, iş yükü iki yolda da aynı mertebede kalır.
"""

from __future__ import annotations

import re
import secrets
from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerifyMismatchError

# Parola politikası — TEK kaynak (router iki kez farklı sınır uygulamasın).
MIN_PASSWORD_LENGTH = 8
# Üst sınır bilinçli: argon2id maliyeti girdi uzunluğuyla büyür — sınırsız
# uzunluk saldırganın CPU'yu ucuza tüketmesine (DoS) izin verir.
MAX_PASSWORD_LENGTH = 128

# E-posta biçimi — tam RFC 5322 doğrulaması DEĞİL (o kütüphane bağımlılığı
# gerektirir, bkz. PR gövdesi); yalnız "açıkça bozuk" girdiyi (boşluk, @ yok,
# nokta yok) reddeden kaba bir kapı. Gerçek doğrulama zaten yoktur (email
# doğrulaması bu dilimde YOK — bkz. D-57 "bilerek yapılmayan").
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Zamanlama savunmasının sahte hedefi — GERÇEK bir DB satırına karşılık
# GELMEZ, yalnızca "argon2 doğrulama iş yükünü tüket" amaçlı bir hash.
#
# Değer KAYNAKTA SABİT YAZILMAZ, süreç başlarken üretilir. İki sebep:
#   1) Sabit bir "..._PASSWORD = '...'" satırı sır tarayıcılarını haklı olarak
#      tetikler (gitleaks `generic-api-key`, CI kırmızı) — tarayıcı bunun
#      gerçek bir kimlik bilgisi OLMADIĞINI bilemez, susturmak yerine kokuyu
#      kaldırıyoruz.
#   2) Kaynakta duran sabit bir "parola" dizgesi, ileride biri onu gerçek bir
#      yerde kopyalarsa gerçek bir açığa dönüşür. Var olmayan değer sızamaz.
#
# Değerin KENDİSİ önemsiz: yalnız `_hasher.hash()`'in gerçek argon2 işini
# yapması gerekiyor; girdinin ne olduğu doğrulama maliyetini değiştirmez.
_DUMMY_PASSWORD = secrets.token_hex(16)

_hasher = PasswordHasher()


class PasswordPolicyError(Exception):
    """Parola politika ihlali — çağıran 422'ye çevirir. Mesaj TÜRKÇE + eyleme
    dönük (doğrudan kullanıcıya gösterilebilir)."""


class EmailFormatError(Exception):
    """E-posta biçimi açıkça bozuk — çağıran 422'ye çevirir."""


def normalize_email(email: str) -> str:
    """TEK normalizasyon kaynağı — kayıt VE giriş yolu bunu çağırmalı.

    `strip()` + `lower()`: `" Ali@X.com "` ile `"ali@x.com"` AYNI benzersizlik
    anahtarına düşer (users.email UNIQUE bu değeri saklar)."""
    return email.strip().lower()


def validate_email_format(normalized_email: str) -> None:
    if not _EMAIL_RE.match(normalized_email):
        raise EmailFormatError("Geçerli bir e-posta adresi girin (örn. ad@ornek.com).")


def validate_password_policy(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"Parola en az {MIN_PASSWORD_LENGTH} karakter olmalı.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"Parola en fazla {MAX_PASSWORD_LENGTH} karakter olabilir.")


def hash_password(password: str) -> str:
    """argon2id hash üret (argon2-cffi varsayılan varyantı — RFC 9106 önerisi)."""
    return _hasher.hash(password)


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    # İlk çağrıda hesaplanır (argon2 hash'leme ~birkaç 10 ms sürer), sonra
    # süreç boyunca ÖNBELLEKTE kalır — her "kullanıcı yok" isteğinde yeniden
    # hesaplanırsa maliyet gerçek yoldan (var olan hash'e karşı TEK doğrulama)
    # FARKLI bir mertebeye kayar (yeniden-hash + doğrulama vs. yalnız doğrulama).
    return _hasher.hash(_DUMMY_PASSWORD)


def verify_password_or_dummy(password_hash: str | None, password: str) -> bool:
    """`password_hash` gerçekse ona karşı doğrular; `None` ise (kullanıcı yok
    YA DA yalnız-GitHub hesap — `password_hash` NULL) yine de SABİT bir sahte
    hash'e karşı GERÇEK bir argon2 doğrulaması çalıştırır ve `False` döner.

    Amaç: `/auth/login`'in "e-posta bulunamadı" ile "parola yanlış" dallarının
    SÜRE PROFİLİ ayrışmasın (#294 brifingi madde 6 — kullanıcı-sayımı/zamanlama
    savunması). Çağıran bu iki durumu AYNI genel hataya (401, "e-posta ya da
    parola hatalı") çevirmelidir — burada AYRIMSIZ `False` dönülür, "neden"
    bilgisi taşınmaz.
    """
    target_hash = password_hash if password_hash is not None else _dummy_hash()
    try:
        _hasher.verify(target_hash, password)
        matched = True
    except VerifyMismatchError:
        matched = False
    except InvalidHash:
        # Bozuk/tanınmayan hash biçimi — güvenlik gereği "eşleşmedi" sayılır,
        # 500'e sızmaz (webhook.py/auth_session.py'deki fail-closed desenin
        # aynısı).
        matched = False
    # `password_hash is None` dalında `matched` teorik olarak True olamaz
    # (gerçek parola sahte hash'e karşı doğrulanıyor) ama açıkça AND'lenir —
    # savunma amaçlı, "yok" bir hesabın ASLA doğrulanmış sayılmaması gerektiği
    # okuyucuya kod okuyarak da (yalnız çalışma zamanı davranışıyla değil)
    # açık olsun diye.
    return matched and password_hash is not None
