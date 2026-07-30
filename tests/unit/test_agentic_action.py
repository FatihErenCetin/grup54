"""Agentic aksiyon (#339) — urunun dis dunyaya ILK YAZMA yolunun kilitleri.

Buradaki her test bir GUARD'i olcer ve guard'i bozunca KIRILIR (mutasyon
kaniti PR aciklamasinda). Ozellikle dikkat: "yazmadi" diye yesil gecen bir
test hicbir sey olcmuyor olabilir — bu yuzden her negatif testin yaninda,
AYNI kurulumun bayrak/durum degisince GERCEKTEN yazdigini gosteren pozitif
bir ikizi var (totolojik test panzehiri).
"""

import logging
from datetime import datetime

import httpx
import pytest

from ensemble.config import Settings
from ensemble.engine.agentic import (
    kararli_kimlik,
    AgenticActionService,
    tespit_isareti,
    yorum_govdesi,
)
from ensemble.engine.radar import DetectionPair, RadarResult
from ensemble.integrations.github.adapter import GitHubAdapter
from ensemble.integrations.github.client import GitHubRestClient
from ensemble.integrations.github.errors import GitHubAuthError, GitHubError
from ensemble.integrations.github.fake import FakeGitHubAdapter
from ensemble.models import Detection, NormalizedEvent


# ---------------------------------------------------------------------------
# yardimcilar
# ---------------------------------------------------------------------------


def _pr_event(
    number: int,
    actor: str,
    branch: str,
    files: list[str],
    damga: str = "2026-07-30T10:00:00",
) -> NormalizedEvent:
    # `damga` PR'a YENI COMMIT gelmesini taklit eder: ingest PR olayini
    # `pr:{numara}:{updated_at}` ile anahtarlar, yani her push id'yi degistirir.
    return NormalizedEvent(
        id=f"pr:{number}:{damga}",
        type="pr",
        actor=actor,
        branch=branch,
        files=files,
        ts=datetime(2026, 7, 30, 10, 0, 0),
        ref=str(number),
    )


def _commit_event(sha: str, actor: str, files: list[str]) -> NormalizedEvent:
    return NormalizedEvent(
        id=f"commit:{sha}",
        type="commit",
        actor=actor,
        branch=None,
        files=files,
        ts=datetime(2026, 7, 30, 9, 0, 0),
        ref=sha,
    )


def _cift(
    *,
    severity: str = "high",
    detection_id: str = "det-1",
    a: NormalizedEvent | None = None,
    b: NormalizedEvent | None = None,
    rationale: str = "Iki dal da judge adaptorunun ayni fonksiyonunu degistiriyor.",
    damga: str = "2026-07-30T10:00:00",
    dosyalar: list[str] | None = None,
) -> DetectionPair:
    dosyalar = dosyalar or ["src/judge.py"]
    a = a or _pr_event(101, "esma", "T-101-judge", dosyalar, damga=damga)
    b = b or _pr_event(202, "enes", "T-202-judge", dosyalar, damga=damga)
    return DetectionPair(
        detection=Detection(
            id=detection_id,
            actors=[a.actor, b.actor],
            branches=[a.branch or "", b.branch or ""],
            files=sorted(set(a.files) | set(b.files)),
            severity=severity,  # type: ignore[arg-type]
            confidence=0.87,
            rationale=rationale,
        ),
        a=a,
        b=b,
        overlap=sorted(set(a.files) & set(b.files)),
    )


def _sonuc(*pairs: DetectionPair) -> RadarResult:
    return RadarResult(
        detections=[pair.detection for pair in pairs],
        evaluated=len(pairs),
        pairs=list(pairs),
    )


class SayanGitHub:
    """HER port cagrisini sayan ikiz — "hic dokunmadi" iddiasini olcmek icin.

    `FakeGitHubAdapter` yalnizca YAZMA cagrilarini biriktirir; "kapali bayrakta
    OKUMA bile yapilmadi" iddiasi ayri bir olcum ister.
    """

    def __init__(self) -> None:
        self.cagrilar: list[str] = []
        self.acik = True
        # Yorumlar PR BASINA ayri: tek ortak liste tutulsaydi, PR #101'e
        # yazilan isaret PR #202'nin taramasinda gorunur ve ikinci PR
        # "zaten_var" diye atlanirdi (ikiz kurulumu, urunun davranisini
        # degil, ikizin hatasini olcerdi — ilk kosuda tam bunu yakaladik).
        self.yorumlar: dict[int, list[str]] = {}

    def pull_request_open(self, number: int) -> bool:
        self.cagrilar.append(f"pull_request_open:{number}")
        return self.acik

    def list_pull_request_comment_bodies(self, number: int) -> list[str]:
        self.cagrilar.append(f"list:{number}")
        return list(self.yorumlar.get(number, []))

    def create_pull_request_comment(self, number: int, body: str) -> str:
        self.cagrilar.append(f"create:{number}")
        self.yorumlar.setdefault(number, []).append(body)
        return "https://example.invalid/1"


class PatlayanGitHub(SayanGitHub):
    def create_pull_request_comment(self, number: int, body: str) -> str:
        self.cagrilar.append(f"create:{number}")
        raise GitHubAuthError("403 izin hatasi: Resource not accessible by integration")


# ---------------------------------------------------------------------------
# 1) Mutlu yol: yuksek siddet -> acik PR'a gerekceli yorum
# ---------------------------------------------------------------------------


def test_yuksek_severity_acik_prlara_gerekceli_yorum_yazar():
    fake = FakeGitHubAdapter()
    servis = AgenticActionService(fake, enabled=True, dry_run=False, max_per_run=5)

    cift = _cift()
    sonuc = servis.run(_sonuc(cift))

    assert sonuc.yazilan == 2, "cakismanin IKI tarafi da acik PR — ikisine de yazilmali"
    assert [numara for numara, _ in fake.yazma_cagrilari] == [101, 202]
    govde = fake.yazma_cagrilari[0][1]
    # Icerik sozlesmesi: kim · hangi dal · kesisen dosyalar · gerekce · kimlik
    assert "esma" in govde and "enes" in govde
    assert "T-101-judge" in govde and "T-202-judge" in govde
    assert "src/judge.py" in govde
    assert "judge adaptorunun ayni fonksiyonunu" in govde
    # Gorunur "Tespit kimligi" satiri ham `Detection.id`yi tasir (insan icin,
    # log ile eslesmesi gerekir); MAKINE isareti ise KARARLI kimlikten turer.
    assert "det-1" in govde
    assert tespit_isareti(kararli_kimlik(cift)) in govde


def test_med_ve_low_hicbir_sey_yazmaz():
    fake = FakeGitHubAdapter()
    servis = AgenticActionService(fake, enabled=True, dry_run=False, max_per_run=5)

    sonuc = servis.run(
        _sonuc(
            _cift(severity="med", detection_id="det-med"),
            _cift(severity="low", detection_id="det-low"),
        )
    )

    assert fake.yazma_cagrilari == []
    assert sonuc.yuksek_tespit == 0
    assert sonuc.outcomes == []


def test_med_low_ile_high_AYNI_kurulumda_ayrisir():
    """Totoloji panzehiri: yukaridaki testin 'yazmadi'si severity filtresinden
    mi geliyor, yoksa kurulum zaten yazamiyor mu? Ayni serviste high olan
    cift YAZILIYOR — demek ki fark severity'den geliyor."""
    fake = FakeGitHubAdapter()
    servis = AgenticActionService(fake, enabled=True, dry_run=False, max_per_run=5)

    # Iki cift FARKLI dosyalarda cakisiyor — aksi halde kararli kimlikleri
    # ayni olur ve test severity farkini degil kimlik cakismasini olcerdi.
    med = _cift(severity="med", detection_id="det-med", dosyalar=["src/med.py"])
    high = _cift(severity="high", detection_id="det-high", dosyalar=["src/high.py"])
    servis.run(_sonuc(med, high))

    yazilan_kimlikler = {govde for _, govde in fake.yazma_cagrilari}
    assert yazilan_kimlikler, "high cift yazilmali (aksi halde test hicbir sey olcmuyor)"
    assert all(tespit_isareti(kararli_kimlik(high)) in govde for govde in yazilan_kimlikler)
    assert all(tespit_isareti(kararli_kimlik(med)) not in govde for govde in yazilan_kimlikler)


# ---------------------------------------------------------------------------
# 2) Idempotency
# ---------------------------------------------------------------------------


def test_ayni_tespit_ikinci_turda_ikinci_yorum_URETMEZ():
    fake = FakeGitHubAdapter()
    servis = AgenticActionService(fake, enabled=True, dry_run=False, max_per_run=5)
    cift = _cift()

    ilk = servis.run(_sonuc(cift))
    ikinci = servis.run(_sonuc(cift))

    assert ilk.yazilan == 2
    assert ikinci.yazilan == 0
    assert [o.sonuc for o in ikinci.outcomes] == ["zaten_var", "zaten_var"]
    assert len(fake.yazma_cagrilari) == 2, "toplam yorum sayisi artmamali"


def test_BASKA_cakisma_ayni_prde_yeni_yorum_uretir():
    """Idempotency'nin 'her seyi bloklayan' bir kilide donmedigini gosterir.

    DIKKAT — bu testin ONCEKI hali `detection_id`yi degistirip iki yorum
    bekliyordu; o, dogrulama turunda bulunan HATAYI sartname olarak kodluyordu
    (bkz. `kararli_kimlik` docstring'i). "Farkli cakisma"nin dogru olcusu
    kimlik dizgesi degil, **kesisen dosya kumesi**dir: ayni iki PR farkli
    dosyalarda da cakisiyorsa bu YENI bir bilgidir, susturulmamalidir.
    """
    fake = FakeGitHubAdapter()
    servis = AgenticActionService(fake, enabled=True, dry_run=False, max_per_run=5)

    servis.run(_sonuc(_cift(dosyalar=["src/judge.py"])))
    servis.run(_sonuc(_cift(dosyalar=["src/radar.py"])))

    assert len(fake.yazma_cagrilari) == 4  # 2 farkli kesisim x 2 PR


def test_PRE_YENI_COMMIT_gelince_AYNI_cakisma_icin_yeni_yorum_YAZILMAZ():
    """DOGRULAMA TURU BULGUSU (30 Tem) — asil regresyon kilidi.

    Isaret `Detection.id`den turedigi surece guard AKTIF bir repoda cokuyordu:
    PR olayinin id'si `pr:{n}:{updated_at}` tasidigi icin her push kimligi
    degistiriyor, ayni cakisma icin yeni yorum yaziliyordu. Olculdu: dort
    turda PR basina dort yorum.

    MUTASYON KILIDI: `kararli_kimlik(pair)` yerine `detection.id` geri
    konursa bu test duser — yani public repoya spam yolu yeniden acilir.
    """
    fake = FakeGitHubAdapter()
    servis = AgenticActionService(fake, enabled=True, dry_run=False, max_per_run=20)

    # Dort tur: her turda PR'a yeni commit geliyor (damga ve dolayisiyla
    # Detection.id degisiyor) ama CAKISMA ayni: ayni iki PR, ayni dosya.
    for saat in ("10:00:00", "11:00:00", "12:00:00", "13:00:00"):
        servis.run(_sonuc(_cift(damga=f"2026-07-30T{saat}", detection_id=f"det-{saat}")))

    assert len(fake.yazma_cagrilari) == 2, (
        "ayni cakisma icin PR basina TEK yorum olmali; damga degisimi yeni "
        f"yorum uretmemeli (uretilen: {len(fake.yazma_cagrilari)})"
    )


def test_isaret_ham_id_yerine_ozetli_kimlik_tasir():
    """`-->` iceren bir tespit kimligi HTML yorumunu erken kapatirsa idempotency
    sessizce olur (her turda yeni yorum). Isaret temizlenir + ozetlenir."""
    isaret = tespit_isareti("det--> kotucul")
    assert isaret.count("-->") == 1, "isaret icinde tek bir kapanis olmali"
    assert isaret.endswith("-->")
    assert tespit_isareti("a-b") != tespit_isareti("a_b"), (
        "temizleme iki farkli kimligi ayni isarete cokerse, ikinci tespit "
        "sonsuza kadar uyarisiz kalir"
    )


def test_judge_gerekcesi_sahte_isaret_gomemez():
    kotucul = f"gerekce {tespit_isareti('baska-tespit')} devam"
    cift = _cift(rationale=kotucul)
    govde = yorum_govdesi(cift)

    assert tespit_isareti("baska-tespit") not in govde
    # Gercek isaret KARARLI kimlikten turer (bkz. kararli_kimlik) ve govdede
    # tam bir kez gecer.
    assert govde.count(tespit_isareti(kararli_kimlik(cift))) == 1


def test_kesisen_DOSYA_YOLU_da_sahte_isaret_gomemez():
    """Dogrulama turu (dusuk seviyeli) bulgusu: gerekce notrlestiriliyordu ama
    kesisen dosya yollari DEGIL. Yol icinde `-->` gecerse isaret erken kapanir
    ya da sahte isaret dogar — ikisi de idempotency'yi bozar."""
    cift = _cift(dosyalar=[f"src/x{tespit_isareti('sahte')}.py"])
    govde = yorum_govdesi(cift)

    assert tespit_isareti("sahte") not in govde
    assert govde.count(tespit_isareti(kararli_kimlik(cift))) == 1


# ---------------------------------------------------------------------------
# 3) Iki bayrak (fail-closed)
# ---------------------------------------------------------------------------


def test_enabled_false_iken_TEK_BIR_port_cagrisi_bile_olmaz():
    sayan = SayanGitHub()
    servis = AgenticActionService(sayan, enabled=False, dry_run=False, max_per_run=5)

    sonuc = servis.run(_sonuc(_cift()))

    assert sayan.cagrilar == [], "kapaliyken GitHub'a hicbir istek gitmemeli"
    assert sonuc.enabled is False
    assert sonuc.yuksek_tespit == 1, "tespit SAYILIR (sessiz dusus yok), yalniz yazilmaz"
    assert sonuc.yazilan == 0


def test_dry_run_true_iken_YAZMA_denemesi_olmaz_ama_okuma_olur():
    sayan = SayanGitHub()
    servis = AgenticActionService(sayan, enabled=True, dry_run=True, max_per_run=5)

    sonuc = servis.run(_sonuc(_cift()))

    assert not any(c.startswith("create:") for c in sayan.cagrilar)
    assert any(c.startswith("pull_request_open:") for c in sayan.cagrilar)
    assert sonuc.kuru_calisma == 2 and sonuc.yazilan == 0


def test_kuru_calisma_ne_yazacagini_LOGLAR(caplog):
    sayan = SayanGitHub()
    servis = AgenticActionService(sayan, enabled=True, dry_run=True, max_per_run=5)

    with caplog.at_level(logging.INFO, logger="ensemble.agentic"):
        servis.run(_sonuc(_cift()))

    metin = caplog.text
    assert "KURU CALISMA" in metin
    assert "src/judge.py" in metin, "log, yazilacak GOVDEYI icermeli"


def test_iki_bayrak_da_acikken_GERCEKTEN_yazar():
    """Yukaridaki iki negatif testin totoloji olmadiginin kaniti."""
    sayan = SayanGitHub()
    servis = AgenticActionService(sayan, enabled=True, dry_run=False, max_per_run=5)

    servis.run(_sonuc(_cift()))

    assert [c for c in sayan.cagrilar if c.startswith("create:")] == ["create:101", "create:202"]


def test_settingsten_kurulum_varsayilanlari_FAIL_CLOSED():
    ayarlar = Settings()
    assert ayarlar.AGENTIC_ACTIONS_ENABLED is False
    assert ayarlar.AGENTIC_ACTIONS_DRY_RUN is True

    servis = AgenticActionService.from_settings(ayarlar, FakeGitHubAdapter())
    assert servis.enabled is False and servis.dry_run is True


def test_kuru_calisma_zorla_yalniz_GUVENLI_yonde_calisir():
    acik = Settings(AGENTIC_ACTIONS_ENABLED=True, AGENTIC_ACTIONS_DRY_RUN=False)

    assert AgenticActionService.from_settings(acik, FakeGitHubAdapter()).dry_run is False
    zorlanmis = AgenticActionService.from_settings(
        acik, FakeGitHubAdapter(), dry_run_zorla=True
    )
    assert zorlanmis.dry_run is True


def test_max_per_run_sifir_kabul_edilmez():
    with pytest.raises(ValueError):
        AgenticActionService(FakeGitHubAdapter(), enabled=True, dry_run=False, max_per_run=0)
    with pytest.raises(ValueError, match="AGENTIC_ACTIONS_MAX_PER_RUN"):
        Settings(AGENTIC_ACTIONS_MAX_PER_RUN=0)


# ---------------------------------------------------------------------------
# 4) Kapali / merge edilmis PR
# ---------------------------------------------------------------------------


def test_kapali_pra_yazilmaz():
    fake = FakeGitHubAdapter()
    fake.acik_prler = {101: False, 202: False}
    servis = AgenticActionService(fake, enabled=True, dry_run=False, max_per_run=5)

    sonuc = servis.run(_sonuc(_cift()))

    assert fake.yazma_cagrilari == []
    assert [o.sonuc for o in sonuc.outcomes] == ["pr_kapali", "pr_kapali"]


def test_kapali_ve_acik_PR_ayni_turda_AYRISIR():
    """Totoloji panzehiri: 'yazmadi' PR durumundan mi geliyor?"""
    fake = FakeGitHubAdapter()
    fake.acik_prler = {101: False, 202: True}
    servis = AgenticActionService(fake, enabled=True, dry_run=False, max_per_run=5)

    sonuc = servis.run(_sonuc(_cift()))

    assert [numara for numara, _ in fake.yazma_cagrilari] == [202]
    assert {o.pr_number: o.sonuc for o in sonuc.outcomes} == {101: "pr_kapali", 202: "yazildi"}


def test_pr_olmayan_cift_sessizce_dusmez():
    fake = FakeGitHubAdapter()
    servis = AgenticActionService(fake, enabled=True, dry_run=False, max_per_run=5)

    sonuc = servis.run(
        _sonuc(
            _cift(
                detection_id="det-commit",
                a=_commit_event("aaa111", "esma", ["src/judge.py"]),
                b=_commit_event("bbb222", "enes", ["src/judge.py"]),
            )
        )
    )

    assert fake.yazma_cagrilari == []
    assert [o.sonuc for o in sonuc.outcomes] == ["hedef_yok"]


# ---------------------------------------------------------------------------
# 5) Tur basina ust sinir
# ---------------------------------------------------------------------------


def test_sinir_asilinca_kalan_LOGLANIR_ve_atlanir(caplog):
    fake = FakeGitHubAdapter()
    servis = AgenticActionService(fake, enabled=True, dry_run=False, max_per_run=1)
    ciftler = [
        _cift(
            detection_id=f"det-{i}",
            a=_pr_event(100 + i, "esma", f"T-{100 + i}-a", ["src/judge.py"]),
            b=_commit_event(f"sha{i}", "enes", ["src/judge.py"]),
        )
        for i in range(3)
    ]

    with caplog.at_level(logging.WARNING, logger="ensemble.agentic"):
        sonuc = servis.run(_sonuc(*ciftler))

    assert len(fake.yazma_cagrilari) == 1
    assert len(sonuc.sinir_asilanlar) == 2
    assert "AGENTIC_ACTIONS_MAX_PER_RUN" in caplog.text
    assert "det-1" in caplog.text and "det-2" in caplog.text
    assert sonuc.degraded is True, "atlanan is varken tur 'temiz' raporlanamaz"


def test_sinir_ZATEN_VAR_olanlari_tuketmez():
    """Livelock kilidi: butce adaylari sayarsaydi, ilk N tespit zaten
    yorumlanmisken YENI bir yuksek cakisma sonsuza kadar uyarisiz kalirdi."""
    fake = FakeGitHubAdapter()
    servis = AgenticActionService(fake, enabled=True, dry_run=False, max_per_run=1)
    eski = _cift(
        detection_id="det-eski",
        a=_pr_event(101, "esma", "T-101-a", ["src/judge.py"]),
        b=_commit_event("sha-eski", "enes", ["src/judge.py"]),
    )
    yeni = _cift(
        detection_id="det-yeni",
        a=_pr_event(202, "semih", "T-202-b", ["src/judge.py"]),
        b=_commit_event("sha-yeni", "fatih", ["src/judge.py"]),
    )

    servis.run(_sonuc(eski))  # butce 1 -> eski yazildi
    fake.yazma_cagrilari.clear()
    sonuc = servis.run(_sonuc(eski, yeni))  # eski zaten var; butce yeniye kalmali

    assert [numara for numara, _ in fake.yazma_cagrilari] == [202]
    assert {o.detection_id: o.sonuc for o in sonuc.outcomes} == {
        "det-eski": "zaten_var",
        "det-yeni": "yazildi",
    }


# ---------------------------------------------------------------------------
# 6) Yazma hatasi yutulmaz
# ---------------------------------------------------------------------------


def test_yazma_hatasi_BASARI_gibi_akmaz(caplog):
    patlayan = PatlayanGitHub()
    servis = AgenticActionService(patlayan, enabled=True, dry_run=False, max_per_run=5)

    with caplog.at_level(logging.ERROR, logger="ensemble.agentic"):
        sonuc = servis.run(_sonuc(_cift()))

    assert sonuc.yazilan == 0, "patlayan yazma ASLA 'yazildi' sayilmaz"
    assert [o.sonuc for o in sonuc.outcomes] == ["hata", "hata"]
    assert "Resource not accessible by integration" in sonuc.hatalar[0].detay
    assert sonuc.degraded is True
    assert "BASARISIZ" in caplog.text


def test_bir_hedefin_hatasi_digerini_DUSURMEZ():
    class YarimPatlayan(SayanGitHub):
        def create_pull_request_comment(self, number: int, body: str) -> str:
            self.cagrilar.append(f"create:{number}")
            if number == 101:
                raise GitHubError("gecici ag hatasi")
            return "https://example.invalid/2"

    port = YarimPatlayan()
    servis = AgenticActionService(port, enabled=True, dry_run=False, max_per_run=5)

    sonuc = servis.run(_sonuc(_cift()))

    assert {o.pr_number: o.sonuc for o in sonuc.outcomes} == {101: "hata", 202: "yazildi"}


def test_okuma_hatasi_da_yutulmaz():
    class OkumaPatlar(SayanGitHub):
        def pull_request_open(self, number: int) -> bool:
            raise GitHubError("PR durumu okunamadi")

    servis = AgenticActionService(OkumaPatlar(), enabled=True, dry_run=False, max_per_run=5)
    sonuc = servis.run(_sonuc(_cift()))

    assert [o.sonuc for o in sonuc.outcomes] == ["hata", "hata"]


# ---------------------------------------------------------------------------
# 7) Gercek adapter: DOGRU GitHub uclari (canliya inen kismin kilidi)
# ---------------------------------------------------------------------------


def _adapter(handler) -> tuple[GitHubAdapter, list[httpx.Request]]:
    istekler: list[httpx.Request] = []

    def _kaydet(request: httpx.Request) -> httpx.Response:
        istekler.append(request)
        return handler(request)

    client = GitHubRestClient(
        token_provider=lambda: "tok",
        http_client=httpx.Client(transport=httpx.MockTransport(_kaydet)),
    )
    ayarlar = Settings(GITHUB_REPO_OWNER="FatihErenCetin", GITHUB_REPO_NAME="grup54")
    return GitHubAdapter(ayarlar, client=client), istekler


def test_adapter_yorumu_ISSUES_ucuna_POSTlar():
    """`/pulls/{n}/comments` satir-ici review yorumudur ve `commit_id`+`path`
    ister — yanlis uc secmek testler yesilken canlida 422 demek olurdu."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"html_url": "https://github.com/x/y/pull/9#c1"})

    adapter, istekler = _adapter(handler)
    url = adapter.create_pull_request_comment(9, "govde")

    assert url == "https://github.com/x/y/pull/9#c1"
    assert istekler[0].method == "POST"
    assert istekler[0].url.path == "/repos/FatihErenCetin/grup54/issues/9/comments"
    assert b'"body"' in istekler[0].content


def test_adapter_izin_yoksa_403_YUKARI_yayilir():
    """App'in `Pull requests: write` izni gelmeden gercek yazma denenirse ne
    olur: sessiz basari DEGIL, GitHubAuthError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "Resource not accessible by integration"})

    adapter, _ = _adapter(handler)
    with pytest.raises(GitHubAuthError):
        adapter.create_pull_request_comment(9, "govde")


@pytest.mark.parametrize(
    "govde, beklenen",
    [
        ({"state": "open", "merged": False}, True),
        ({"state": "closed", "merged": False}, False),
        ({"state": "closed", "merged": True}, False),
        # merge edilmis ama state alani "open" gelirse bile YAZMA:
        ({"state": "open", "merged": True}, False),
        ({"state": "open", "merged_at": "2026-07-29T10:00:00Z"}, False),
    ],
)
def test_adapter_pr_acikligi_iki_bagimsiz_sinyale_bakar(govde, beklenen):
    adapter, _ = _adapter(lambda request: httpx.Response(200, json=govde))
    assert adapter.pull_request_open(9) is beklenen


def test_adapter_pr_durumu_okunamazsa_KAPALI_demez():
    """`None` govde -> `False` donmek 'PR kapali' YALANINI uretirdi."""
    adapter, _ = _adapter(lambda request: httpx.Response(304))
    with pytest.raises(GitHubError):
        adapter.pull_request_open(9)


def test_adapter_yorum_taramasi_sayfalar_ve_her_sayfaya_kendi_etagini_verir():
    sayfalar = {
        "1": [{"body": f"yorum-{i}"} for i in range(100)],
        "2": [{"body": "son-yorum"}],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        sayfa = request.url.params.get("page")
        return httpx.Response(
            200, json=sayfalar[sayfa], headers={"ETag": f'W/"sayfa-{sayfa}"'}
        )

    adapter, istekler = _adapter(handler)
    bodies = adapter.list_pull_request_comment_bodies(9)

    assert len(bodies) == 101 and bodies[-1] == "son-yorum"
    assert [i.url.params.get("page") for i in istekler] == ["1", "2"]


def test_adapter_yorumlar_bitmezse_SESSIZCE_kirpmaz():
    """20 sayfa dolu gelirse isaret taranmamis olabilir — 'yorum yok' demek
    her turda YENI yorum uretirdi."""

    def handler(request: httpx.Request) -> httpx.Response:
        sayfa = request.url.params.get("page")
        return httpx.Response(
            200,
            json=[{"body": "x"} for _ in range(100)],
            headers={"ETag": f'W/"p{sayfa}"'},
        )

    adapter, _ = _adapter(handler)
    with pytest.raises(GitHubError, match="idempotency"):
        adapter.list_pull_request_comment_bodies(9)


# ---------------------------------------------------------------------------
# 8) RadarResult.pairs — tespit ile onu ureten olaylarin baglantisi
# ---------------------------------------------------------------------------


def test_radar_pairs_detectionlarla_ayni_sirada_ve_ayni_kumede():
    from ensemble.integrations.gemini.fake import FakeJudgeAdapter
    from ensemble.engine.radar import RadarService

    olaylar = [
        _pr_event(101, "esma", "T-101-a", ["src/judge.py", "src/a.py"]),
        _pr_event(202, "enes", "T-202-b", ["src/judge.py"]),
        _pr_event(303, "semih", "T-303-c", ["src/a.py"]),
    ]

    class Statik:
        def fetch_events(self, since):
            return list(olaylar)

        def fetch_backfill_events(self, limit_per_type=50):
            return list(olaylar)

        def compare(self, base, head):
            return []

        def get_diff(self, base, head):
            return {}

    sonuc = RadarService(
        github_port=Statik(), judge_port=FakeJudgeAdapter(), backfill_limit=0
    ).collect()

    assert [pair.detection for pair in sonuc.pairs] == sonuc.detections
    for pair in sonuc.pairs:
        assert set(pair.overlap) == set(pair.a.files) & set(pair.b.files)


# ---------------------------------------------------------------------------
# 9) Giris noktasi (son santim: bu kod CANLIDA nasil kosturulur)
# ---------------------------------------------------------------------------


def _cli_kurulumu(monkeypatch, ayarlar: Settings, github_port):
    """`main()`in agir bagimliliklarini (DB motoru, radar insasi) degistirir."""
    import ensemble.app as app_modulu
    import ensemble.config as config_modulu
    import ensemble.store.engine as store_engine

    radar = type(
        "SahteRadar",
        (),
        {"github_port": github_port, "collect": staticmethod(lambda: _sonuc(_cift()))},
    )()
    monkeypatch.setattr(store_engine, "get_engine", lambda settings: None)
    monkeypatch.setattr(store_engine, "get_session_factory", lambda engine: None)
    monkeypatch.setattr(app_modulu, "_build_radar_service", lambda *a, **k: radar)
    monkeypatch.setattr(config_modulu, "get_settings", lambda: ayarlar)


def test_cli_gercek_yazmayi_FAKE_adapterla_REDDEDER(monkeypatch, capsys):
    """Gercek App yapilandirmasi yokken 'yazdim' diye rapor etmek, hicbir sey
    yapmamaktan daha kotudur (D-51 kapisinin ayni ruhu)."""
    from ensemble.agentic_cli import main

    fake = FakeGitHubAdapter()
    _cli_kurulumu(
        monkeypatch,
        Settings(AGENTIC_ACTIONS_ENABLED=True, AGENTIC_ACTIONS_DRY_RUN=False),
        fake,
    )

    kod = main([])

    assert kod == 2
    assert "REDDEDILDI" in capsys.readouterr().err
    assert fake.yazma_cagrilari == []


def test_cli_gercek_port_ile_REDDETMEZ(monkeypatch, capsys):
    """Totoloji panzehiri: yukaridaki 2 kodu 'her zaman reddediyor'dan mi
    geliyor? Fake OLMAYAN bir port ile ayni yapilandirma calisir."""
    from ensemble.agentic_cli import main

    port = SayanGitHub()
    _cli_kurulumu(
        monkeypatch,
        Settings(AGENTIC_ACTIONS_ENABLED=True, AGENTIC_ACTIONS_DRY_RUN=False),
        port,
    )

    kod = main([])

    assert kod == 0
    assert [c for c in port.cagrilar if c.startswith("create:")]
    assert "yazilan yorum    : 2" in capsys.readouterr().out


def test_cli_kuru_calisma_bayragi_yazmayi_kapatir(monkeypatch, capsys):
    from ensemble.agentic_cli import main

    port = SayanGitHub()
    _cli_kurulumu(
        monkeypatch,
        Settings(AGENTIC_ACTIONS_ENABLED=True, AGENTIC_ACTIONS_DRY_RUN=False),
        port,
    )

    kod = main(["--kuru-calisma"])

    assert kod == 0
    assert not [c for c in port.cagrilar if c.startswith("create:")]
    assert "kuru calisma     : 2" in capsys.readouterr().out


def test_cli_hata_varsa_sifir_disi_kod_doner(monkeypatch, capsys):
    from ensemble.agentic_cli import main

    _cli_kurulumu(
        monkeypatch,
        Settings(AGENTIC_ACTIONS_ENABLED=True, AGENTIC_ACTIONS_DRY_RUN=False),
        PatlayanGitHub(),
    )

    assert main([]) == 1


def test_modul_girisi_GERCEKTEN_kosturulabilir():
    """SON SANTIM: `python -m ensemble.agentic_cli` uretim imajinda (venv'de
    kurulu paket) kosacak komuttur. Burada AYNI cagri bicimi alt surecte
    denenir — import zinciri kirilsa ya da modul adi degisse KIRMIZI."""
    import subprocess
    import sys as _sys

    tamamlanan = subprocess.run(
        [_sys.executable, "-m", "ensemble.agentic_cli", "--help"],
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert tamamlanan.returncode == 0, tamamlanan.stderr
    assert "--kuru-calisma" in tamamlanan.stdout


def test_runbook_uretimde_IMAJDA_OLMAYAN_bir_ikili_cagirmaz():
    """SON SANTIM kilidi (bu repoda bir kez yasandi): runbook mukemmel bir
    komut yazar, komut prod imajinda calismaz.

    Prod imaji `COPY --from=builder /app /app` yapar — `Makefile` imaja HIC
    kopyalanmaz, `make`/`uv` runtime katmaninda YOKTUR. Bu yuzden runbook'un
    agentic bolumu `python -m ensemble.agentic_cli` demek ZORUNDA.
    """
    from pathlib import Path

    runbook = (
        Path(__file__).resolve().parents[2] / "docs" / "deploy-runbook.md"
    ).read_text(encoding="utf-8")
    bolum = runbook.split("## 10. Agentic aksiyon", 1)
    assert len(bolum) == 2, "deploy-runbook.md'de '## 10. Agentic aksiyon' bolumu yok"
    metin = bolum[1]

    assert "docker compose exec api python -m ensemble.agentic_cli" in metin
    for satir in metin.splitlines():
        if "docker compose exec" in satir and not satir.lstrip().startswith(">"):
            assert " make " not in satir and not satir.strip().endswith("make"), (
                f"konteyner icinde `make` cagriliyor ama imajda make YOK: {satir!r}"
            )
