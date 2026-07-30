"""SQLAlchemy 2.0 modelleri — projeksiyon tabloları (#41).

NormalizedEvent (#16) ve .harness/ (#13) verisinin hızlı-sorgu projeksiyonu.
Kanonik DEĞİL — .harness/ + GitHub her zaman kazanır; bu tablolar
rebuild_projection() ile yeniden kurulabilir (rebuildable cache).

`UserRow` (T-294/D-57) İSTİSNA — bu tablo bir projeksiyon/cache DEĞİLDİR,
`.harness/`'ten türetilemez; email+parola üyeliğinin KENDİSİ (kanonik veri).
PO kararı (D-57) `internal/grup54_dizin_yapisi.md` §5'teki eski "users/
accounts/profiles tablosu YOK" iddiasını bu tabloya özel olarak geçersiz
kıldı — bkz. `.harness/decisions/D-57-email-parola-uyeligi.md`.

Çok-kiracılık (#79 kalan dilim, T-79): `IdentityRow`/`InstallationRow`/
`WatchedRepoRow` de kanonik veridir (`.harness/`'ten türetilemez — bir GitHub
App kurulumunun kim tarafından/hangi repo için yapıldığı yalnızca GitHub'ın
kendisinde ve burada yaşar). Beş projeksiyon tablosu (`EventRow`,
`TaskProjectionRow`, `PresenceRow`, `TaskStatusEventRow`) artık `repo_full_name`
taşır ve BİLEREK bunu birincil anahtarın PARÇASI yapar — `id`/`task_id`/
`handle`/`(source_event_id, task_id)` tek başına GLOBAL benzersiz DEĞİLDİR
(örn. PR numarası her repoda 1'den başlar; `T-51` her repoda ayrı bir görev
olabilir). Yalnızca `repo_full_name` eklemek ama PK'yi GENİŞLETMEMEK iki farklı
kiracının aynı `id`'yi paylaştığı an sessiz bir üzerine-yazmaya (isolation
ihlali) yol açardı — bkz. `.harness/decisions/D-58-cok-kiracili-repo-secimi.md`.
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    true as sa_true,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ensemble.models import BoardCard, NormalizedEvent

# Tek-kiracılı/çok-kiracılık-DIŞI çağıranların (mevcut testlerin çoğu, tek
# repo varsayan yardımcı script'ler) `repo_full_name` hiç geçmediğinde
# düştüğü SABİT kiracı — "filtre yok" (fail-open) DEĞİL, "filtre HER ZAMAN
# var, verilmezse bu sabit değere düşer" (bkz. store/rebuild.py,
# engine/projector.py, engine/board.py, engine/events.py, engine/graph.py).
# Üretim DI'sı (ensemble/tenancy.py) HİÇBİR ZAMAN bu varsayılana güvenmez,
# her zaman gerçek `repo_full_name`'i açıkça geçer.
DEFAULT_REPO_FULL_NAME = "default/repo"


class Base(DeclarativeBase):
    """Tüm projeksiyon tablolarının temel sınıfı."""


class EventRow(Base):
    """NormalizedEvent'in DB projeksiyonu — ingest çıktısı (#16).

    PK `(id, repo_full_name)` (T-79) — `id` TEK BAŞINA global benzersiz
    DEĞİLDİR: `pr:{number}:{updated_at}`/`issue:{number}:{updated_at}` gibi
    kimlikler PR/issue NUMARASINDAN türer ve numaralar her repoda 1'den
    başlar (bkz. integrations/github/normalize.py). `repo_full_name`'i PK'ye
    KATMAMAK, iki farklı kiracının PR #1'inin aynı satırı paylaşmasına
    (sessiz üzerine-yazma) yol açardı.

    `actor_verified` (#296, T-296): `NormalizedEvent.actor_verified`'in DB
    kolonu. `server_default=true` BİLİNÇLİ — hem yeni satırların Python
    tarafında alanı unutarak INSERT etmesi hem de bu migration'ın backfill
    ettiği ESKİ satırlar (PO kararı: mevcut olası eşleşmeyen satırlara
    dokunulmaz, bkz. #296 "kısa vadeli temizlik" notu) aynı güvenli
    varsayılana (`True`, "doğrulanmış") düşer — geçmiş yeniden yorumlanmaz.
    """

    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    repo_full_name: Mapped[str] = mapped_column(String(255), primary_key=True, index=True)
    type: Mapped[str] = mapped_column(String(20))
    actor: Mapped[str] = mapped_column(String(255), index=True)
    branch: Mapped[str | None] = mapped_column(String(255))
    files: Mapped[list] = mapped_column(JSON, default=list)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    ref: Mapped[str] = mapped_column(String(255))
    actor_verified: Mapped[bool] = mapped_column(Boolean, default=True, server_default=sa_true())

    def to_domain(self) -> NormalizedEvent:
        """DB satırından Pydantic modeline dönüştür.

        `repo_full_name` BİLEREK taşınmaz — `NormalizedEvent` (domain/engine
        sözleşmesi, docs/sprint2-kontratlar.md) kiracıdan HABERSİZDİR; tenant
        scoping yalnızca bu DB-satırı katmanında yaşar (engine sıfır dokunuş).
        """
        return NormalizedEvent(
            id=self.id,
            type=self.type,
            actor=self.actor,
            branch=self.branch,
            files=self.files,
            ts=self.ts,
            ref=self.ref,
            actor_verified=self.actor_verified,
        )

    @classmethod
    def from_domain(cls, event: NormalizedEvent, *, repo_full_name: str) -> "EventRow":
        """Pydantic modelinden DB satırına dönüştür — `repo_full_name` çağıranın
        (Projector/rebuild) sorumluluğudur, `NormalizedEvent`'te YOKTUR."""
        return cls(
            id=event.id,
            repo_full_name=repo_full_name,
            type=event.type,
            actor=event.actor,
            branch=event.branch,
            files=event.files,
            ts=event.ts,
            ref=event.ref,
            actor_verified=event.actor_verified,
        )


class TaskProjectionRow(Base):
    """.harness/tasks/ projeksiyonu — board'ın hızlı-sorgu cache'i.

    Durum modeli (D-55, İş 2): `status` GERÇEK kanonik değerdir — `seed_status`
    (.harness dosyasındaki tohum) ile `task_status_events` tablosundaki
    geçişlerin `fold_status()` ile katlanmasının SONUCUDUR. `seed_status`
    yalnızca fold'un başlangıç noktasını ayrı tutmak için saklanır; .harness
    dosyası elle düzenlenip tohum değişse bile birikmiş geçişler yeniden
    katlanınca aynı `status`'e ulaşılır (bkz. store/rebuild.py fold_status).
    """

    __tablename__ = "task_projection"

    task_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    # PK'nin parçası (T-79) — `T-51` gibi bir task_id her repoda ayrı bir
    # göreve karşılık gelebilir (issue numaraları repo başına sıfırlanır).
    repo_full_name: Mapped[str] = mapped_column(String(255), primary_key=True, index=True)
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), index=True, default="backlog")
    seed_status: Mapped[str] = mapped_column(String(20), default="backlog")
    assignee: Mapped[str | None] = mapped_column(String(255))
    ref: Mapped[str | None] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_transition_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    def to_board_card(self) -> BoardCard:
        """DB satırından BoardCard Pydantic modeline dönüştür (kiracıdan
        habersiz — `BoardCard` #33 B1 kontratı, `repo_full_name` taşımaz)."""
        return BoardCard(
            task_id=self.task_id,
            title=self.title,
            status=self.status,
            assignee=self.assignee,
            ref=self.ref,
        )

    @classmethod
    def from_harness(cls, data: dict, *, repo_full_name: str) -> "TaskProjectionRow":
        """Harness task dict'inden DB satırına dönüştür (tohum satırı).

        data: HarnessPort.read_tasks() çıktısındaki tek bir task dict'i.
        Beklenen alanlar: task_id (veya id), title, status, assignee, ref.

        `status` burada yalnızca TOHUM değeridir (`seed_status` ile aynı
        başlar) — rebuild_projection() bunun üzerine task_status_events'i
        katlayıp gerçek `status`'ü belirler.
        """
        seed = data.get("status", "backlog")
        return cls(
            task_id=data.get("task_id") or data.get("id", ""),
            repo_full_name=repo_full_name,
            title=data.get("title", ""),
            status=seed,
            seed_status=seed,
            assignee=data.get("assignee"),
            ref=data.get("ref"),
        )

    @classmethod
    def from_github_issue(cls, issue: dict, *, repo_full_name: str) -> "TaskProjectionRow":
        """Ham GitHub issue kaynağından kart satırı — `.harness`'te DOSYASI
        OLMAYAN gerçek işler için (#331).

        Neden gerekli: kart kümesi `.harness/tasks/`'la sınırlıyken repoda
        ~150 issue varken board'da 22 kart vardı; bugün açılan gerçek işler
        (`T-319`/`T-324`/`T-327`) `unmatched` diye loglanıp panoya HİÇ
        düşmüyordu — "kendiliğinden DOLAN board" vaadi tam burada kırılıyordu.

        Tohum BİLEREK `backlog`: issue'nun açık/kapalı olduğu bilgisi tohuma
        GÖMÜLMEZ, aynı GitHub anlık görüntüsünden `transitions_from_resources`
        ile GEÇİŞ olarak üretilir ve fold ile katlanır (tek kural, iki yol
        yerine). "Kapalı issue'yu doğrudan done tohumla" kestirmesi durumu
        `task_status_events` günlüğünden KOPARIR — kanıtsız bir done olurdu.

        `ref`, `#<numara>` olarak doldurulur: `.harness` tohumlu kartlarda bu
        alan boştur, dolu olması kartın kaynağını UI'da görünür kılar.
        """
        number = issue["number"]
        assignee = (issue.get("assignee") or {}).get("login")
        if not assignee:
            assignees = issue.get("assignees") or []
            assignee = (assignees[0] or {}).get("login") if assignees else None
        return cls(
            task_id=f"T-{number}",
            repo_full_name=repo_full_name,
            title=issue.get("title") or "",
            status="backlog",
            seed_status="backlog",
            assignee=assignee,
            ref=f"#{number}",
        )


class PresenceRow(Base):
    """.harness/active/ projeksiyonu — kim ne üzerinde çalışıyor (canlı varlık)."""

    __tablename__ = "presence"

    handle: Mapped[str] = mapped_column(String(255), primary_key=True)
    # PK'nin parçası (T-79) — aynı kişi (handle) birden çok kiracıda eş
    # zamanlı aktif olabilir; her kiracının kendi presence satırı olmalı.
    repo_full_name: Mapped[str] = mapped_column(String(255), primary_key=True, index=True)
    task: Mapped[str | None] = mapped_column(String(50))
    module: Mapped[str | None] = mapped_column(String(255))
    intent: Mapped[str | None] = mapped_column(Text)
    branch: Mapped[str | None] = mapped_column(String(255))
    since: Mapped[datetime | None] = mapped_column(DateTime)

    @classmethod
    def from_harness(cls, data: dict, *, repo_full_name: str) -> "PresenceRow":
        """Harness active dict'inden DB satırına dönüştür.

        data: HarnessPort.read_active() çıktısındaki tek bir active dict'i
        (active.schema.json alan adları: handle, task_id, module, intent,
        branch, updated_at — updated_at şemada string olarak zorunlu, bu
        yüzden DateTime kolonuna yazmadan önce parse ediyoruz).
        """
        updated_at = data.get("updated_at")
        return cls(
            handle=data.get("handle", ""),
            repo_full_name=repo_full_name,
            task=data.get("task_id"),
            module=data.get("module"),
            intent=data.get("intent"),
            branch=data.get("branch"),
            since=datetime.fromisoformat(updated_at) if updated_at else None,
        )


class TaskStatusEventRow(Base):
    """Kalıcı durum günlüğü — GERÇEK GitHub PR/issue olayından türetilen durum
    geçişleri (D-55, İş 2). Append-only: aynı (source_event_id, task_id) ikinci
    kez yazılmaya çalışıldığında satır ÇOĞALMAZ (bkz. store/rebuild.py
    append_status_events) — GitHub'ın aynı webhook'u yeniden teslim etmesi
    (retry) durumu bozmaz.

    Bileşik PK BİLEREK (source_event_id, task_id): tek bir PR event'i hem
    branch'ten (T-<id>) hem gövdedeki her `Closes #N`'den birden fazla farklı
    task için geçiş üretebilir — PK yalnız source_event_id olsaydı bu ikinci
    task'ın satırı ilkini ezerdi (bkz. tests/unit/test_rebuild.py
    test_ayni_olay_iki_kez_yazilinca_cogalmaz).

    `status` burada ÇÖZÜLMÜŞ hedef durumdur (ham GitHub event tipi değil) —
    üretimi engine/status_rules.py'nin sorumluluğudur (İş 1); bu tablo yalnız
    sonucu kalıcılaştırır. `resets` monotonluğu BİLEREK kıran geçişleri işaretler
    (örn. issue reopened → todo); `fold_status()` bunu bilgi amaçlı taşır.
    """

    __tablename__ = "task_status_events"

    source_event_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(50), primary_key=True, index=True)
    # PK'nin parçası (T-79) — `source_event_id` ("pr:{n}:...", "issue:{n}:...")
    # PR/issue NUMARASINDAN türer, `task_id` de ("T-{n}") aynı şekilde; ikisi
    # de repo başına sıfırlanan sayaçlardır — repo_full_name olmadan iki
    # kiracının aynı numaralı PR'ı AYNI satırı paylaşır (redelivery koruması
    # yanlışlıkla başka bir kiracının geçişini "zaten işlendi" sayar).
    repo_full_name: Mapped[str] = mapped_column(String(255), primary_key=True, index=True)
    status: Mapped[str] = mapped_column(String(20))
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    reason: Mapped[str | None] = mapped_column(String(255))
    resets: Mapped[bool] = mapped_column(Boolean, default=False)


class JudgeVerdictRow(Base):
    """Kalıcı judge yargı önbelleği (#259) — `CachedConflictJudge` (bellek,
    TTL'li) MISS verince bir sonraki katmanın (`PersistentJudge`) baktığı
    kalıcı depo. Konteyner yeniden yaratıldığında (CD, #236) bellek katmanı
    her seferinde sıfırlanır ama bu tablo KALICI kalır — aynı çift için
    Gemini/Groq'a ikinci kez ödenmez.

    `cache_key`, `engine/cache.py::_digest`'in ÜRETTİĞİ AYNI içerik-adresli
    anahtardır (a+b+overlap+sim üzerinden sha256) — kaç KATTIR ki `model`de
    bu anahtara KATILMIŞ olmalıdır (çağıranın sorumluluğu, bkz.
    `verdict_store.py`): aynı çift farklı bir model tarafından yargılanınca
    farklı bir `cache_key` üretilir, eski satırın üzerine YAZILMAZ — farklı
    model farklı yargı verir, model değişince eski yargılar sessizce
    "doğru" gibi kullanılmaz. `model` kolonu AYRICA (anahtarın parçası olsa
    bile) düz metin olarak saklanır — yalnızca bayatlık teşhisi/gözlem
    içindir (örn. "şu modelin ürettiği kaç yargı var" sorgusu), PK'nin
    KENDİSİ değildir.

    `detection`, `Detection.model_dump(mode="json")` çıktısıdır; okurken
    `Detection.model_validate(...)` ile geri kurulur (bkz. verdict_store.py
    `get_verdict`). Bozuk/eski şemalı bir satır okunursa `verdict_store.py`
    sessizce `None` döner (log'lu) — bu MEŞRU bir geçiş yoludur, yargı
    yeniden hesaplanır.

    `JudgeUnavailableError` BURAYA HİÇ YAZILMAZ (#252 sözleşmesi): hata bir
    sonuç değildir, kalıcılaştırılmaz — bu tablo yalnızca GERÇEK yargıları
    tutar (bkz. `ports.py::JudgeUnavailableError` docstring'i).
    """

    __tablename__ = "judge_verdicts"

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    model: Mapped[str] = mapped_column(String(100), index=True)
    detection: Mapped[dict] = mapped_column(JSON)
    # #264 (Semih blocker B): bu sütun ÖNCE yalnızca gözlem içindi, hiçbir
    # okuma yolu KULLANMIYORDU. Artık `verdict_store.py::get_verdict`'in
    # (opsiyonel) `ttl_days` karşılaştırmasında OKUNUR — `put_verdict` bu
    # sütunu HEM ilk INSERT'te HEM de mevcut satırın üzerine her yazışta
    # `datetime.utcnow()`'a tazeler (kolon varsayılanı yalnızca INSERT'te
    # devreye girer, UPDATE'te tazelenmez — bkz. o fonksiyonun docstring'i).
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
# Vektör kolonu burada YOK — #15 (Semih) ekleyecek.
# pgvector extension migration'ı ayrı bir alembic adımında (002_pgvector_extension.py).


class UserRow(Base):
    """Email + parola ile gerçek üyelik (T-294/D-57) — "GitHub ile gir"
    akışının YANINDA, onun yerine değil.

    GÜNCELLEME (T-79, çok-kiracılı repo seçimi): D-57 döneminde "GitHub OAuth
    oturumları BU TABLOYA YAZMAZ" diyen eski kural artık DOĞRU DEĞİL —
    installation picker (`installations`/`watched_repos`) bir `user_id`'ye
    ihtiyaç duyar, bu yüzden `api/routers/auth.py::github_oauth_callback`
    artık `identities` üzerinden get-or-create bir `UserRow` açar (bkz.
    `IdentityRow`). Bu, D-57'nin "hesap BİRLEŞTİRME kapsam dışı" kararını
    İHLAL ETMEZ — burada birleştirme YOK, yalnızca GitHub kimliğinin KENDİ
    (yeni) satırı açılıyor; email ile GitHub hesabı hâlâ ayrı satırlardır.

    `password_hash` NULL => yalnız-GitHub hesabı (`/auth/register`'dan
    GEÇMEDİ — GitHub OAuth callback'inden get-or-create ile açıldı).
    `github_handle` NULL => yalnız-email hesabı (`/auth/register`'dan geçti).

    CHECK kısıtı (`ck_users_auth_method_present`) ikisinin BİRDEN NULL olduğu
    bir satırı REDDEDER — kimlik doğrulama yolu olmayan "hayalet" bir hesap
    hiçbir zaman DB'ye yazılamaz (mutasyon kanıtı: PR gövdesi).

    Email BENZERSİZLİĞİ normalize edilmiş değer üzerindendir — bu tablo
    kendisi normalize ETMEZ (`ensemble.api.credentials.normalize_email`in
    işi); `store/user_store.py` yalnızca ZATEN normalize edilmiş bir email
    BEKLER. İki farklı normalize noktası aynı kişiye iki satır açardı (#294
    brifingi madde 2) — normalize tek fonksiyonda, çağıran (router) bir kez
    uygular.

    `active_repo_full_name` (T-79): kullanıcının o an "izlediği" tek repo —
    `TenantDep` (api/deps.py) bunu okuyup engine servislerini buna göre
    kiracılar. `watched_repos`'taki bir satırı işaret ETMELİDİR (`PUT
    /auth/repos` bunu doğrular); tutarsız/silinmiş bir repoyu işaret ederse
    `TenantDep` sessizce demo repo'ya düşer (fail-closed, uydurma veri YOK).
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "password_hash IS NOT NULL OR github_handle IS NOT NULL",
            name="ck_users_auth_method_present",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    github_handle: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True, index=True
    )
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    active_repo_full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)


class IdentityRow(Base):
    """Sağlayıcı kimliği -> `users.id` eşlemesi (T-79).

    Bugün TEK sağlayıcı: `provider="github"`, `provider_user_id`=GitHub'ın
    SAYISAL kullanıcı id'si (handle DEĞİL — handle değişebilir, sayısal id
    değişmez; bkz. `integrations/github/oauth.py::fetch_github_user`).
    `unique(provider, provider_user_id)` aynı GitHub hesabının iki kez
    `UserRow` açmasını engeller (get-or-create bu tabloyu ÖNCE kontrol eder).

    Bu tablo D-57'nin "hesap birleştirme kapsam dışı" kararını GENİŞLETMEZ —
    yalnızca "bu GitHub kimliği hangi `users` satırına karşılık geliyor"
    sorusuna cevap verir; email hesabıyla otomatik birleştirme YAPMAZ.
    """

    __tablename__ = "identities"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_identities_provider_user"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class InstallationRow(Base):
    """Bir kullanıcının kurduğu GitHub App kurulumu (T-79 — Installation
    picker). Kalıcı token SAKLANMAZ — yalnızca GitHub'ın verdiği
    `installation_id` (App JWT + bu id ile installation-token HER İSTEKTE
    anlık üretilir, bkz. `ensemble/tenancy.py`). `account_login` yalnız
    GÖRÜNÜM amaçlı (UI'da "hangi hesap/organizasyon" göstermek için); yetki
    kararı asla buna dayanmaz, `installation_id`'ye dayanır.
    """

    __tablename__ = "installations"

    installation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_login: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class WatchedRepoRow(Base):
    """Kullanıcının seçtiği izlenecek repo seti (T-79 — `PUT /auth/repos`).

    PK `(user_id, repo_full_name)` — bir kullanıcı aynı repoyu iki kez
    izleyemez (upsert semantiği). `installation_id`, bu (user, repo) çiftinin
    HANGİ kurulum üzerinden erişildiğini taşır — `TenantDep` bunu okuyup
    o kurulumun anlık token'ıyla GitHub'a gider (kalıcı token YOK).
    """

    __tablename__ = "watched_repos"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), primary_key=True)
    repo_full_name: Mapped[str] = mapped_column(String(255), primary_key=True)
    installation_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("installations.installation_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
