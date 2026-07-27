import pytest
from google.genai import types

import ensemble.integrations.gemini.embeddings as embeddings_module
from ensemble.config import Settings
from ensemble.integrations.gemini.client import ResilientGeminiClient
from ensemble.integrations.gemini.embeddings import GeminiEmbeddingsAdapter
from ensemble.integrations.gemini.errors import GeminiPermanentError, GeminiTransientError


class _StubEmbeddingClient:
    def __init__(self):
        self.calls: list[tuple[tuple[str, ...], str]] = []

    def embed_content(self, texts: list[str], *, task_type: str) -> list[list[float]]:
        self.calls.append((tuple(texts), task_type))
        return [[float(index), 1.0] for index, _text in enumerate(texts)]


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, GEMINI_API_KEY="fake-key", **overrides)


def test_gemini_embeddings_adapter_delegates_batch_and_task_type():
    client = _StubEmbeddingClient()
    adapter = GeminiEmbeddingsAdapter(_settings(), client=client)

    vectors = adapter.embed(["a", "b"], task_type="SEMANTIC_SIMILARITY")

    assert vectors == [[0.0, 1.0], [1.0, 1.0]]
    assert client.calls == [(("a", "b"), "SEMANTIC_SIMILARITY")]


def test_gemini_embeddings_adapter_empty_batch_skips_client():
    client = _StubEmbeddingClient()
    adapter = GeminiEmbeddingsAdapter(_settings(), client=client)

    assert adapter.embed([], task_type="SEMANTIC_SIMILARITY") == []
    assert client.calls == []


def test_gemini_embeddings_adapter_clienti_ilk_batchte_bir_kez_kurar(monkeypatch):
    created: list[_StubEmbeddingClient] = []

    def build_client(settings: Settings) -> _StubEmbeddingClient:
        del settings
        client = _StubEmbeddingClient()
        created.append(client)
        return client

    monkeypatch.setattr(embeddings_module, "ResilientGeminiClient", build_client)
    adapter = GeminiEmbeddingsAdapter(_settings())

    adapter.embed(["a"], task_type="RETRIEVAL_DOCUMENT")
    adapter.embed(["b"], task_type="RETRIEVAL_QUERY")

    assert len(created) == 1
    assert created[0].calls == [
        (("a",), "RETRIEVAL_DOCUMENT"),
        (("b",), "RETRIEVAL_QUERY"),
    ]


class _FakeApiError(Exception):
    def __init__(self, code: int, mesaj: str | None = None):
        self.code = code
        # Varsayilan mesaj korunuyor (mevcut testler aynen calisir); 429
        # senaryolarinda gercek govdeyi taklit etmek icin `mesaj` verilir.
        super().__init__(mesaj or f"api error {code}")


class _FakeEmbeddingModels:
    def __init__(self, fail_times: int = 0, fail_code: int = 503):
        self.fail_times = fail_times
        self.fail_code = fail_code
        self.calls = 0
        self.last_model = None
        self.last_contents = None
        self.last_config = None

    def embed_content(self, model: str, contents: list[str], config=None):
        self.calls += 1
        self.last_model = model
        self.last_contents = contents
        self.last_config = config
        if self.calls <= self.fail_times:
            raise _FakeApiError(self.fail_code)
        return types.EmbedContentResponse(
            embeddings=[
                types.ContentEmbedding(values=[float(index), 0.5])
                for index, _text in enumerate(contents)
            ]
        )


class _FakeSdkClient:
    def __init__(self, models: _FakeEmbeddingModels):
        self.models = models


def _patch_genai_client(monkeypatch, fake_models: _FakeEmbeddingModels) -> None:
    import ensemble.integrations.gemini.client as client_module

    monkeypatch.setattr(client_module.genai_errors, "APIError", _FakeApiError, raising=False)
    monkeypatch.setattr(
        client_module.genai,
        "Client",
        lambda **kwargs: _FakeSdkClient(fake_models),
    )


def test_resilient_client_embeds_with_model_task_type_and_dimensions(monkeypatch):
    fake_models = _FakeEmbeddingModels()
    _patch_genai_client(monkeypatch, fake_models)
    client = ResilientGeminiClient(
        _settings(
            GEMINI_EMBEDDING_MODEL="gemini-embedding-001",
            GEMINI_EMBEDDING_DIMENSIONS=768,
        )
    )

    vectors = client.embed_content(["a", "b"], task_type="SEMANTIC_SIMILARITY")

    assert vectors == [[0.0, 0.5], [1.0, 0.5]]
    assert fake_models.last_model == "gemini-embedding-001"
    assert fake_models.last_contents == ["a", "b"]
    assert fake_models.last_config.task_type == "SEMANTIC_SIMILARITY"
    assert fake_models.last_config.output_dimensionality == 768


def test_resilient_client_embedding_retries_transient_errors(monkeypatch):
    fake_models = _FakeEmbeddingModels(fail_times=2, fail_code=503)
    _patch_genai_client(monkeypatch, fake_models)
    client = ResilientGeminiClient(_settings(GEMINI_MAX_RETRIES=5))

    assert client.embed_content(["a"], task_type="SEMANTIC_SIMILARITY") == [[0.0, 0.5]]
    assert fake_models.calls == 3


def test_resilient_client_embedding_permanent_error_not_retried(monkeypatch):
    fake_models = _FakeEmbeddingModels(fail_times=10, fail_code=401)
    _patch_genai_client(monkeypatch, fake_models)
    client = ResilientGeminiClient(_settings(GEMINI_MAX_RETRIES=5))

    with pytest.raises(GeminiPermanentError):
        client.embed_content(["a"], task_type="SEMANTIC_SIMILARITY")
    assert fake_models.calls == 1


def test_resilient_client_embedding_exhausts_transient_retries(monkeypatch):
    fake_models = _FakeEmbeddingModels(fail_times=10, fail_code=503)
    _patch_genai_client(monkeypatch, fake_models)
    client = ResilientGeminiClient(_settings(GEMINI_MAX_RETRIES=3))

    with pytest.raises(GeminiTransientError):
        client.embed_content(["a"], task_type="SEMANTIC_SIMILARITY")
    assert fake_models.calls == 3


def test_resilient_client_rejects_short_embedding_batch(monkeypatch):
    class _ShortModels(_FakeEmbeddingModels):
        def embed_content(self, model: str, contents: list[str], config=None):
            self.calls += 1
            return types.EmbedContentResponse(embeddings=[types.ContentEmbedding(values=[1.0])])

    fake_models = _ShortModels()
    _patch_genai_client(monkeypatch, fake_models)
    client = ResilientGeminiClient(_settings())

    with pytest.raises(GeminiPermanentError, match="one vector per text"):
        client.embed_content(["a", "b"], task_type="SEMANTIC_SIMILARITY")


# ---------------------------------------------------------------------------
# Batch tavani (#280 takibi) - Gemini tek cagrida en fazla 100 istek alir
# ---------------------------------------------------------------------------


class _BatchSayanModels:
    """Her cagrinin BOYUTUNU kaydeder ve metni vektore GERI IZLENEBILIR gomer.

    Vektorun ilk bileseni metnin kendi sirasi -> sira korunuyor mu, olculebilir.
    """

    def __init__(self, tavan: int = 100):
        self.boyutlar: list[int] = []
        self._tavan = tavan

    def embed_content(self, model: str, contents: list[str], config=None):
        self.boyutlar.append(len(contents))
        if len(contents) > self._tavan:
            # Gercek API'nin davranisi: 400 INVALID_ARGUMENT
            raise _FakeApiError(400)
        return types.EmbedContentResponse(
            embeddings=[
                types.ContentEmbedding(values=[float(t.split("-")[1]), 0.5])
                for t in contents
            ]
        )


def test_embed_content_100_USTU_girdiyi_parcalar(monkeypatch):
    """MUTASYON KILIDI: parcalama kaldirilirsa sahte API 400 firlatir.

    Gercek dusus (uretim, 2026-07-27): #280 gecmis backfill'i 250 olaya
    cikarinca `make rebuild` TAMAMEN dustu --
      400 INVALID_ARGUMENT: at most 100 requests can be in one batch
    Tavan cagri BASINA; toplam girdiye sinir yok, parcalamak yeterli.
    """
    modeller = _BatchSayanModels()
    _patch_genai_client(monkeypatch, modeller)
    client = ResilientGeminiClient(_settings())

    metinler = [f"olay-{i}" for i in range(250)]
    vektorler = client.embed_content(metinler, task_type="SEMANTIC_SIMILARITY")

    assert len(vektorler) == 250, "her metne bir vektor donmeli"
    assert max(modeller.boyutlar) <= 100, (
        f"hicbir cagri 100'u asmamali; gorulen boyutlar: {modeller.boyutlar}"
    )
    assert modeller.boyutlar == [100, 100, 50], (
        f"250 girdi 100/100/50 diye bolunmeli; gorulen: {modeller.boyutlar}"
    )


def test_parcalama_SIRAYI_bozmaz(monkeypatch):
    """Parca sinirinda kayma olsa vektorler YANLIS olaya baglanirdi -- ve bu
    hicbir hata vermeden, yalnizca benzerlik skorlarini bozarak olurdu."""
    modeller = _BatchSayanModels()
    _patch_genai_client(monkeypatch, modeller)
    client = ResilientGeminiClient(_settings())

    metinler = [f"olay-{i}" for i in range(250)]
    vektorler = client.embed_content(metinler, task_type="SEMANTIC_SIMILARITY")

    # Sahte model vektorun ilk bilesenine metnin kendi numarasini koyuyor.
    assert [int(v[0]) for v in vektorler] == list(range(250)), (
        "vektor sirasi girdi sirasiyla birebir eslesmeli (parca sinirinda kayma yok)"
    )


def test_tek_parca_gerektiginde_FAZLADAN_cagri_yok(monkeypatch):
    """100 ve alti tek cagri kalmali -- parcalama eskiyi pahalilastirmiyor."""
    modeller = _BatchSayanModels()
    _patch_genai_client(monkeypatch, modeller)
    client = ResilientGeminiClient(_settings())

    client.embed_content([f"olay-{i}" for i in range(100)], task_type="SEMANTIC_SIMILARITY")
    assert modeller.boyutlar == [100], f"tek cagri bekleniyordu: {modeller.boyutlar}"


# ---------------------------------------------------------------------------
# Sunucunun dayattigi bekleme (429 retryDelay) - uretimde olculdu
# ---------------------------------------------------------------------------


def test_sunucunun_bekleme_suresi_GERCEK_429_govdesini_ayristirir():
    """Uretimde alinan gercek govde (2026-07-27, ucretsiz katman embed kotasi)."""
    from ensemble.integrations.gemini.errors import sunucunun_bekleme_suresi

    gercek = (
        "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded "
        "your current quota... Please retry in 30.192357358s. \\n* Quota exceeded "
        "for metric: generativelanguage.googleapis.com/embed_content_free_tier_"
        "requests, limit: 100', 'status': 'RESOURCE_EXHAUSTED', 'details': "
        "[{'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '30s'}]}}"
    )
    assert sunucunun_bekleme_suresi(gercek) == pytest.approx(30.19, abs=0.01)


def test_sunucunun_bekleme_suresi_UYDURMAZ():
    """Ayristirilamayan/absurt girdide `None` -- varsayilan bir sayi UYDURULMAZ.

    Yanlis bir sure, hic sure olmamasindan beter: erken uyanip kotayi tekrar
    yakar ve retry butcesini bosa harcar.
    """
    from ensemble.integrations.gemini.errors import sunucunun_bekleme_suresi

    assert sunucunun_bekleme_suresi("connection reset by peer") is None
    assert sunucunun_bekleme_suresi("retryDelay: '99999s'") is None, "absurt deger reddedilmeli"
    assert sunucunun_bekleme_suresi("retryDelay: '-5s'") is None, "negatif reddedilmeli"


def test_429_dayatilan_sureyi_TASIR_ve_backoff_ONA_uyar():
    """MUTASYON KILIDI: `_bekleme` sarmalayicisi kaldirilirsa bekleme 8 sn
    tavanina duser ve kota penceresi (60 sn) dolmadan retry'lar tukenir --
    uretimde `make rebuild` tam olarak boyle dustu.
    """
    from ensemble.integrations.gemini.client import _bekleme, _classify

    class _Sahte429(Exception):
        code = 429

        def __str__(self):
            return "429 RESOURCE_EXHAUSTED. Please retry in 30.1s."

    hata = _classify(_Sahte429())
    assert isinstance(hata, GeminiTransientError)
    assert hata.retry_after == pytest.approx(30.1, abs=0.01), (
        "429'un dayattigi sure hataya taşınmali"
    )

    class _SahteSonuc:
        @staticmethod
        def exception():
            return hata

    class _SahteDurum:
        outcome = _SahteSonuc()

    bekle = _bekleme(lambda _s: 8.0)  # varsayilan backoff tavani
    assert bekle(_SahteDurum()) == pytest.approx(31.1, abs=0.01), (
        "sunucunun suresi + 1 sn pay kullanilmali, 8 sn'lik varsayilan DEGIL"
    )


def test_dayatilan_sure_yoksa_NORMAL_backoff_kalir():
    """Sunucu sure vermediginde eski davranis aynen surer (regresyon yok)."""
    from ensemble.integrations.gemini.client import _bekleme

    class _SahteSonuc:
        @staticmethod
        def exception():
            return GeminiTransientError("baglanti koptu")  # retry_after yok

    class _SahteDurum:
        outcome = _SahteSonuc()

    assert _bekleme(lambda _s: 8.0)(_SahteDurum()) == 8.0


def test_retry_GERCEKTEN_dayatilan_sure_kadar_bekler(monkeypatch):
    """UCTAN UCA kilit: dekoratorlerin `_bekleme`'yi KULLANDIGINI kanitlar.

    Onceki test `_bekleme`'yi tek basina cagiriyordu; sarmalayici retry
    dekoratorlerinden silinse bile YESIL kaliyordu (mutasyonla goruldu).
    Burada gercek uyku suresini yakaliyoruz.
    """
    uykular: list[float] = []
    import tenacity.nap

    monkeypatch.setattr(tenacity.nap.time, "sleep", lambda s: uykular.append(s))

    class _Kota429Models:
        def __init__(self):
            self.calls = 0

        def embed_content(self, model, contents, config=None):
            self.calls += 1
            if self.calls == 1:
                # Gercek govde: sunucu bekleme suresini SOYLUYOR.
                raise _FakeApiError(
                    429,
                    "429 RESOURCE_EXHAUSTED. Please retry in 30.0s. "
                    "{'details': [{'@type': '...RetryInfo', 'retryDelay': '30s'}]}",
                )
            return types.EmbedContentResponse(
                embeddings=[types.ContentEmbedding(values=[0.0, 0.5]) for _ in contents]
            )

    modeller = _Kota429Models()
    _patch_genai_client(monkeypatch, modeller)
    # Sinir BILEREK yuksek: bu test "sarmalayici dekoratore bagli mi" sorusunu
    # kiliyor, kirpma davranisini degil (onu `test_dayatilan_sure_UST_SINIRLA_
    # kirpilir` olcuyor). Varsayilan 10 sn'lik sinirla 30 sn'lik dayatma
    # kirpilirdi ve iki farkli sey tek testte karisirdi.
    client = ResilientGeminiClient(
        _settings(GEMINI_MAX_RETRIES=3, GEMINI_RETRY_AFTER_CAP_S=120.0)
    )

    client.embed_content(["a"], task_type="SEMANTIC_SIMILARITY")

    assert uykular, "retry hic beklemedi"
    assert uykular[0] == pytest.approx(31.0, abs=0.01), (
        f"sunucunun dayattigi 30 sn + 1 sn pay beklenirdi, uyunan: {uykular[0]:.2f} sn "
        "-- dekoratorlerden `_bekleme` silinmis olabilir (8 sn tavanina duser)"
    )


# ---------------------------------------------------------------------------
# retryDelay UST SINIRI — interaktif yol ile toplu yolun ihtiyaci farkli
# ---------------------------------------------------------------------------


def test_dayatilan_sure_UST_SINIRLA_kirpilir():
    """MUTASYON KILIDI: sinir kaldirilirsa interaktif istek 24 sn bekler.

    Uretimde olculdu (2026-07-27): Gemini generate kotasi GUNDE 20 istek;
    tukendiginde `retryDelay: 23s` geliyor ama pencere YARIN aciliyor --
    beklemek hicbir sey kazandirmiyor. `/radar` 66.7 saniye surup sonunda
    yine "degerlendiremedik" diyordu. Erken pes edip durust cevap vermek,
    gec pes edip AYNI cevabi vermekten iyidir.
    """
    from ensemble.integrations.gemini.client import _bekleme

    class _Sonuc:
        @staticmethod
        def exception():
            return GeminiTransientError("429", retry_after=23.0)

    class _Durum:
        outcome = _Sonuc()

    bekle = _bekleme(lambda _s: 8.0, lambda: 10.0)
    assert bekle(_Durum()) == 10.0, "24 sn istenmisti, 10 sn'lik sinira kirpilmali"


def test_ust_sinir_YUKSELTILEBILIR_toplu_isler_icin():
    """`rebuild` gibi toplu isler gercekten bekleyebilmeli -- kirpma orada
    ZARARLI olurdu (embed kotasi dakikalik, beklemek ISE YARIYOR: `make
    rebuild` tam da bu sayede 250'den 663 olaya cikti)."""
    from ensemble.integrations.gemini.client import _bekleme

    class _Sonuc:
        @staticmethod
        def exception():
            return GeminiTransientError("429", retry_after=27.0)

    class _Durum:
        outcome = _Sonuc()

    assert _bekleme(lambda _s: 8.0, lambda: 120.0)(_Durum()) == 28.0


def test_sinir_ALTINDA_kalan_sure_kirpilmaz():
    """Kisa bir dayatma (or. 3 sn) oldugu gibi kullanilmali."""
    from ensemble.integrations.gemini.client import _bekleme

    class _Sonuc:
        @staticmethod
        def exception():
            return GeminiTransientError("429", retry_after=3.0)

    class _Durum:
        outcome = _Sonuc()

    assert _bekleme(lambda _s: 8.0, lambda: 10.0)(_Durum()) == 4.0
