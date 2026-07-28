from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# .env her zaman repo kökünden yüklenir (cwd'den bağımsız — alt dizinden
# çalıştırınca sessizce varsayılana düşme tuzağı kapalı). Dosya yoksa atlanır.
_REPO_ROOT = Path(__file__).resolve().parents[3]


def normalize_local_ollama_url(value: str) -> str:
    """`OLLAMA_BASE_URL` biçim kuralı — TEK kaynak (#78 loopback zorunluluğu).

    Hem `Settings.OLLAMA_BASE_URL` alan doğrulayıcısı (açılış-anı, `.env`den)
    HEM DE T-307 FAZ 2 (`PUT /settings/saglayici`, kullanıcı ayarlar sayfasından
    kaydettiğinde) AYNI kuralı uygulamalı — iki ayrı kopya (biri burada, biri
    router'da) sessizce KAYARSA biri loopback-dışı bir adresi kabul edip
    diğeri reddedebilir (repo bağlamının makineden çıkmama garantisi ikisinden
    BİRİNDE delinir). `ValueError` fırlatır — çağıran (Settings validator'ı ya
    da router) kendi hata biçimine (pydantic ValidationError / HTTP 422) çevirir.
    """
    normalized = value.rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme != "http" or parsed.hostname not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise ValueError("OLLAMA_BASE_URL yerel bir HTTP loopback adresi olmali (#78)")
    return normalized


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_REPO_ROOT / ".env"), extra="ignore")

    ENSEMBLE_MODE: Literal["local", "hosted"] = "local"
    ENSEMBLE_ALLOW_FAKE_SEED: bool = False

    # LLM saglayicisi calisma modundan bagimsizdir (#78): local engine Gemini,
    # hosted engine Ollama (ayni makinede) kullanabilir. Varsayilan, geriye
    # uyumluluk icin Gemini'dir.
    LLM_PROVIDER: Literal["gemini", "ollama"] = "gemini"

    # Tarayıcı CORS allowlist'i (#45) — asla "*". Env'de virgüllü tek satır
    # (CORS_ORIGINS=https://a.example,https://b.example). NoDecode: pydantic-settings
    # liste alanını JSON sanıp parse etmeye kalkmasın, ham string validator'a düşsün.
    CORS_ORIGINS: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _decode_cors_origins(cls, v: object) -> object:
        # Env virgüllü tek satır gönderir (düz metin → liste); "*" hangi kaynaktan
        # gelirse gelsin güvenlik gereği açılışta reddedilir (#45).
        if isinstance(v, str):
            v = [parca.strip() for parca in v.split(",") if parca.strip()]
        if isinstance(v, (list, tuple)) and "*" in v:
            raise ValueError("CORS allowlist '*' içeremez (#45)")
        return v

    # Gemini (embeddings + judge) — key yoksa da Settings çökmemeli (fake adapter
    # key gerektirmez); key eksikliği yalnızca ResilientGeminiClient somutlaştırılırken kontrol edilir.
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # --- Groq: judge icin YEDEK saglayici (#255) ---
    # GROQ_API_KEY set edilirse judge FallbackJudge(birincil, Groq) ile
    # sarilir. Bos ise hicbir sey degismez - yedek OPSIYONEL, kurulum
    # zorunlulugu getirmez. Gerekce: olculen ucretsiz Gemini kotasi
    # 20 istek/gun (flash) ve 10 istek/dakika (flash-lite); tek soguk
    # /radar 131 judge cagrisi yapiyor.
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_BASE_URL: str = "https://api.groq.com"
    GROQ_TIMEOUT_S: float = 30.0
    GROQ_MAX_RETRIES: int = 3
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-001"
    GEMINI_EMBEDDING_DIMENSIONS: int = 768
    GEMINI_TIMEOUT_S: float = 10.0
    GEMINI_MAX_RETRIES: int = 3

    # Ollama tam-yerel modu (#78). Loopback zorunlulugu repo baglaminin yanlis
    # yapilandirma ile baska bir makineye tasinmasini engeller.
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_MODEL: str = "llama3.2"
    OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text"
    OLLAMA_EMBEDDING_DIMENSIONS: int = 768
    OLLAMA_TIMEOUT_S: float = 60.0
    OLLAMA_MAX_RETRIES: int = 2

    @field_validator("OLLAMA_BASE_URL")
    @classmethod
    def _validate_local_ollama_url(cls, value: str) -> str:
        return normalize_local_ollama_url(value)

    # GitHub App (machine auth - ingest, #16). Hepsi opsiyonel - FakeGitHubAdapter
    # gerektirmez; eksikse GitHubAdapter/InstallationTokenCache somutlastirilirken
    # GitHubConfigError firlatilir.
    GITHUB_APP_ID: str | None = None
    GITHUB_APP_PRIVATE_KEY_PATH: str | None = None
    # Hosted alternatifi (#186) - Fly/Render secret'lari env-STRING, mount'lu
    # dosya degil. PATH varsa PATH kazanir (mevcut local akis); PATH yoksa bu
    # alanin (PEM icerigi, ham metin) kullanilir.
    GITHUB_APP_PRIVATE_KEY: str | None = None
    GITHUB_APP_INSTALLATION_ID: str | None = None
    GITHUB_REPO_OWNER: str | None = None
    GITHUB_REPO_NAME: str | None = None
    GITHUB_DEFAULT_BRANCH: str = "main"
    GITHUB_BACKFILL_LIMIT: int = 50
    # RADAR'in ilk doldurmasi. Kucuk tutulur: radar adaylari cift olarak
    # uretir (combinations, kare buyur) ve her cift bir judge cagrisi eder --
    # 50 olay zaten ~90 aday demek. Buyutmek dogrudan kotayi yakar.
    #
    # PROJEKSIYONUN (Activity akisi, Graph, board) ihtiyaci BAMBASKA: orada
    # cift YOK, yalniz olay listesi var; maliyet dogrusal ve tek seferlik.
    # Ayni sayiyi paylastiklarinda radar guvenli kalsin diye akis 5 haftalik
    # gecmisi kaybediyordu (olculdu: repo 19 Haziran'dan beri ~250 commit,
    # akis 21 Temmuz'dan geriye gitmiyordu). Iki farkli ihtiyac, iki ayar.
    GITHUB_HISTORY_LIMIT: int = 500
    # Backend frontend'i KENDISI servis etsin mi (tek surecli masaustu paketi).
    #
    # ACIK BAYRAK, otomatik tespit DEGIL. Eskiden "dist/ varsa mount et"
    # deniyordu ve bu, uygulamanin davranisini "birinin `npm run build`
    # calistirip calistirmadigina" baglıyordu: CI'da dist/ yok -> API 404
    # doner; gelistiricinin makinesinde dist/ var -> ayni yol SPA'ya duser.
    # Iki test tam bu yuzden yerelde kirmizi, CI'da yesildi (olculdu).
    # Sunucuda birinin frontend derlemesi de backend'i sessizce farkli
    # davrandirirdi. Paket ve compose bunu ACIKCA acar.
    ENSEMBLE_SERVE_FRONTEND: bool = False
    # 429'da sunucunun dayattigi `retryDelay`'e uyariz (#283) ama INSANIN
    # BEKLEDIGI istekte bu sinirla kirpilir. Olculdu (2026-07-27): Gemini
    # generate kotasi GUNDE 20; tukendiginde `retryDelay: 23s` geliyor ama
    # pencere yarin aciliyor -- 23 sn beklemek hicbir sey kazandirmiyor,
    # `/radar` 66.7 sn suruyordu ve sonunda yine "degerlendiremedik" diyordu.
    # Erken pes edip DURUST cevap vermek daha iyi. Toplu isler (`rebuild`)
    # bunu yukseltip gercekten bekleyebilir.
    GEMINI_RETRY_AFTER_CAP_S: float = 10.0
    # Judge asamasi I/O-bagimli: canlida 131 aday SIRALI olarak 129 sn surerken
    # konteyner CPU'su %0.7-6 arasindaydi (#254). Ust sinir saglayicinin RPM
    # tavani; 1 yapmak paralelligi tamamen kapatir (sirali yol korunur).
    RADAR_JUDGE_CONCURRENCY: int = 8
    # Webhook receiver (#62) - X-Hub-Signature-256 HMAC dogrulamasi icin.
    # Yoksa receiver 503 doner (dogrulanamayan webhook kabul edilmez).
    GITHUB_WEBHOOK_SECRET: str | None = None

    # Store — local: SQLite (repo kökünde, gitignored) · hosted: PostgreSQL DSN.
    # Varsayılan SQLite yolu: ensemble.db (repo kökü, .gitignore'da).
    DATABASE_URL: str = f"sqlite:///{_REPO_ROOT / 'ensemble.db'}"

    # --- Kalıcı judge yargı TTL'si (#264, Semih blocker B) ---
    # `judge_verdicts` tablosu (engine/persistence.py + store/verdict_store.py,
    # #259) `created_at` sütununu TAŞIYORDU ama HİÇBİR okuma yolu
    # KULLANMIYORDU — DB'deki bir yargı sonsuza kadar servis edilirdi.
    # Risk: `cache_key` a/b/overlap/sim/model'den üretilir (bkz.
    # `engine/persistence.py`); rubriğin KENDİSİ (`gemini/judge.py::
    # _build_prompt`) anahtara KATILMAZ — rubrik değişince (örn. severity
    # eşiği kalibre edilince) eski satırlar farklı bir rubrikle üretilmiş
    # olsa bile aynı anahtarla eşleşmeye sonsuza dek devam ederdi.
    #
    # Varsayılan 7 gün — iki yönde de sınırlı, bilinçli bir denge:
    #   - ÇOK KISA olursa #259'un TÜM amacı (konteyner yeniden yaratmanın,
    #     CD #236, Gemini/Groq faturasını SIFIRLAMASI) kaybolur — her
    #     restart yeniden ödeme demektir.
    #   - ÇOK UZUN (ya da bugünkü gibi sınırsız) olursa prompt/model
    #     değişikliği sessizce sonsuza dek gizlenir (yukarıdaki risk).
    # 7 gün tipik bir sprint döngüsünden kısa (rubrik/model değişikliği
    # genelde bu aralıkta olur) ama günlük CD restart'ları arasında bolca
    # kalır. Süresi geçmiş satır SİLİNMEZ, yalnızca okunmaz sayılır —
    # gerekçe: `store/verdict_store.py::get_verdict` docstring'i.
    VERDICT_TTL_DAYS: float = 7.0

    @field_validator("VERDICT_TTL_DAYS")
    @classmethod
    def _validate_verdict_ttl_days(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("VERDICT_TTL_DAYS pozitif olmali (#264)")
        return value

    # Radar eşikleri (#151, kalibre: #18) — 0.0/0.0 kalibrasyon SONUCU, placeholder
    # değil: sweep (#29) 60 kombinasyonun hiçbirinde FP eklemeden recall
    # kazandırmıyor — mevcut korpuste FP'yi engelleyen gate/judge katmanı,
    # jaccard/similarity değil. Detay + şerhler: eval/kalibrasyon-raporu.md
    RADAR_WINDOW_DAYS: int = 14
    RADAR_MIN_JACCARD: float = 0.0
    RADAR_MIN_SIMILARITY: float = 0.0

    # --- Hosted public demo sertlestirme (#63) — VARSAYILAN KAPALI ---
    # local/dev davranisi bu bayrak acilmadan HIC degismez.
    DEMO_MODE: bool = False
    DEMO_RATE_WINDOW_S: int = 60
    DEMO_AI_RATE_LIMIT: int = 10  # IP basina, KULLANICI-GIRDILI AI yollari (/query, /scope/check)
    DEMO_AI_GLOBAL_LIMIT: int = 60  # tum IP'ler toplami — asil fatura tavani
    DEMO_RATE_LIMIT: int = 120  # IP basina, diger (poll'lanan) yollar
    DEMO_CACHE_TTL_S: int = 900
    # 256'ydi -> RADAR_WINDOW_DAYS(14)+GITHUB_BACKFILL_LIMIT(50) altinda calisma
    # kumesi (~300 farkli metin: commit/diff cifti + query/scope adaylari)
    # bu siniri asiyor ve LRU tahliyesi surekli TERS etki yapiyordu (thrashing:
    # sinirsizken ~300 embed cagrisi, 256-limitli calismada ~900'e cikiyordu -
    # ayni metinler pencere icinde tekrar tekrar Gemini'ye gidiyordu, tam da
    # bu cache'in onlemesi gereken sey). 1024: calisma kumesinin ~3.4x'i (guvenli
    # pay) - bellek olcumu (768-dim float listesi, gercek Python nesnesi):
    # sys.getsizeof ile ~24.6 KB/vektor -> 1024 * 24.6 KB =~ 25 MB, 512 MB Fly
    # VM'in ~%5'i (F1 kontrat kaydi #63 - deger burada ve .env.example'da,
    # docs/sprint3-kontratlar.md Ek F/F1'deki kod blogu da 1024 gosterir - AYNI
    # commit'te senkronlandi; test_config.py::
    # test_demo_cache_max_entries_dokuman_ile_ayni bu ikisinin bir daha
    # kaymamasini kilitler).
    DEMO_CACHE_MAX_ENTRIES: int = 1024

    @model_validator(mode="after")
    def _validate_demo_mode(self) -> "Settings":
        # Fail-closed acilis: DEMO_MODE acikken tek read-only repo'ya sabitlenme
        # ZORUNLU (#63) - yoksa uygulama hic ayaga kalkmaz (auth_blocked kanit
        # yerine tasarim-anı garanti).
        if self.DEMO_MODE and not (self.GITHUB_REPO_OWNER and self.GITHUB_REPO_NAME):
            raise ValueError(
                "DEMO_MODE tek repo'ya sabitlenmeden acilamaz (#63) — "
                "GITHUB_REPO_OWNER ve GITHUB_REPO_NAME zorunlu"
            )
        _positive_fields = (
            "DEMO_RATE_WINDOW_S",
            "DEMO_AI_RATE_LIMIT",
            "DEMO_AI_GLOBAL_LIMIT",
            "DEMO_RATE_LIMIT",
            "DEMO_CACHE_TTL_S",
            "DEMO_CACHE_MAX_ENTRIES",
        )
        for field in _positive_fields:
            if getattr(self, field) <= 0:
                raise ValueError(f"{field} pozitif olmali (#63)")
        return self

    @property
    def demo_repo_full_name(self) -> str | None:
        if not (self.GITHUB_REPO_OWNER and self.GITHUB_REPO_NAME):
            return None
        return f"{self.GITHUB_REPO_OWNER}/{self.GITHUB_REPO_NAME}"

    # --- Kullanıcı girişi (GitHub App kullanıcı-yetkilendirme akışı, #79
    # daraltılmış dilim) — VARSAYILAN KAPALI: hiçbiri set edilmemişse
    # /auth/config {"enabled": false} döner, /auth/login 503 verir; TÜM
    # DİĞER UÇLAR (radar/board/scope/query/...) bundan ETKİLENMEZ — giriş
    # yalnızca "kim olduğunu göster" katmanıdır, uygulamayı KAPATMAZ.
    # access_token BU AKIŞTA HİÇBİR YERDE SAKLANMAZ (ne DB ne cache) — yalnız
    # callback içinde `/user` çağrısı için kullanılır, sonra atılır
    # (integrations/github/oauth.py). Kullanıcı/identity tablosu, installation
    # picker, çok-kiracılık = #79'un AYRI/kalan dilimi — bu bayraklar yalnız
    # tek-repo (#63 pin) tek-kullanıcı-oturumu akışını açar.
    GITHUB_OAUTH_CLIENT_ID: str | None = None
    GITHUB_OAUTH_CLIENT_SECRET: str | None = None
    # Oturum çerezini imzalayan HMAC anahtarı — `itsdangerous` YERİNE stdlib
    # `hmac` (webhook.py::verify_signature ile AYNI desen, GITHUB_WEBHOOK_SECRET
    # ikizi; bkz. api/auth_session.py).
    AUTH_SESSION_SECRET: str | None = None
    # callback başarıyla bittiğinde tarayıcının döneceği yer (frontend rotası).
    # MUTLAK URL OLMAK ZORUNDA (şema + host dahil) — callback FastAPI'de
    # (api.<domain>) çalışır ve `RedirectResponse` bir GÖRELİ yol (örn.
    # "/radar") alırsa tarayıcı bunu MEVCUT (api) origin'ine karşı çözer,
    # frontend origin'ine değil. Üretimde tam olarak bu yaşandı: kod
    # varsayılanı göreli "/radar" idi, giriş "başarılı" görünüyordu ama
    # tarayıcı `https://api.recommend2me.com/radar`'a düşüyordu — orada
    # sayfa yok, sessiz 404 (#258). Sunucuda mutlak URL ile elle düzeltildi;
    # varsayılan burada de facto DOĞRU (aşağıdaki local doğrulayıcı) ve yanlış
    # (göreli) bir değer artık açılışta REDDEDİLİR — CORS_ORIGINS'in "*"
    # reddi ve DEMO_MODE'un repo-pin zorunluluğuyla AYNI fail-closed desen:
    # yanlış yapılandırma sessizce 404 üretmek yerine uygulamayı hiç
    # başlatmaz. Üretim değeri (`https://recommend2me.com/radar`) BİLEREK
    # burada hardcode EDİLMEDİ — hangi origin'in "doğru" olduğu ortama göre
    # değişir; tek güvenli varsayılan yereldir (CORS_ORIGINS'in local
    # girdileriyle AYNI köken: http://localhost:5173).
    AUTH_POST_LOGIN_URL: str = "http://localhost:5173/radar"
    # Çerez Domain'i — paylaşılan üst alan adından türetilir (örn.
    # "ensemble-demo.com") ki api.<domain> ve app.<domain> aynı çerezi
    # paylaşabilsin; yerelde None kalır (Domain set edilmez, localhost çalışır).
    AUTH_COOKIE_DOMAIN: str | None = None

    @field_validator("AUTH_POST_LOGIN_URL")
    @classmethod
    def _validate_auth_post_login_url_absolute(cls, value: str) -> str:
        # Fail-SAFE değil fail-OPEN olurdu: göreli bir yolu "olduğu gibi"
        # kabul edip RedirectResponse'a öylece geçirmek — tarayıcı onu
        # sessizce API origin'ine karşı çözer, giriş "302 döndü" diye BAŞARILI
        # raporlanır ama kullanıcı 404'e düşer (#258'in ta kendisi). Burada
        # bunun yerine gerçek hata sinyali (ValidationError, açılışta patlar)
        # veriliyor — "yokluk" ile ayırt edilemeyen sahte bir varsayılana
        # ASLA çökmüyor.
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(
                "AUTH_POST_LOGIN_URL MUTLAK bir URL olmalı, şema+host dahil "
                f"(örn. 'https://app.example.com/radar') — göreli bir yol "
                f"(alınan: {value!r}) callback'in çalıştığı API origin'ine "
                "karşı çözülür, frontend origin'ine DEĞİL (#258 üretim "
                "olayı: '/radar' -> https://api.recommend2me.com/radar -> "
                "404, sessizce). Yerelde varsayılanı kullan "
                "(http://localhost:5173/radar) ya da gerçek frontend "
                "origin'ini mutlak yaz."
            )
        return value

    @property
    def auth_enabled(self) -> bool:
        """`/auth/login` + `/auth/callback` (GitHub OAuth) fail-closed açılışı
        için TEK kaynak — üçü de set edilmeden giriş asla açılmaz (imzasız/
        doğrulanamaz bir çerez asla üretilmez). `/auth/config` de bunu
        birebir yayınlar."""
        return bool(
            self.GITHUB_OAUTH_CLIENT_ID
            and self.GITHUB_OAUTH_CLIENT_SECRET
            and self.AUTH_SESSION_SECRET
        )

    @property
    def email_auth_enabled(self) -> bool:
        """`/auth/register` + `/auth/login` (email+parola, T-294/D-57) fail-
        closed açılışı için TEK kaynak. GitHub OAuth'tan (`auth_enabled`)
        BAĞIMSIZDIR — email akışı `GITHUB_OAUTH_*` gerektirmez, yalnızca
        `AUTH_SESSION_SECRET`e ihtiyaç duyar (oturum çerezini imzalamak için;
        `sign_session` bu sır olmadan çağrılamaz — bkz. api/auth_session.py).
        `/auth/config` bunu `email_enabled` alanıyla yayınlar (frontend hangi
        formu göstereceğini bilsin)."""
        return bool(self.AUTH_SESSION_SECRET)

    @property
    def app_auth_enabled(self) -> bool:
        """`/auth/install-url` + `/auth/installations` (T-79 — Installation
        picker) fail-closed açılışı için TEK kaynak. `GITHUB_OAUTH_*`'tan
        (`auth_enabled`, kullanıcı girişi) BAĞIMSIZDIR — bunlar App'in
        KENDİSİ adına (JWT ile) konuşur, kullanıcı-yetkilendirme akışını
        gerektirmez. `AUTH_SESSION_SECRET` de ZORUNLU — bu uçlar oturum
        gerektirir (kim adına kurulum yapıldığını bilmek için)."""
        return bool(
            self.GITHUB_APP_ID
            and (self.GITHUB_APP_PRIVATE_KEY_PATH or self.GITHUB_APP_PRIVATE_KEY)
            and self.AUTH_SESSION_SECRET
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
