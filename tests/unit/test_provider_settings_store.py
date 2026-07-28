"""`store/provider_settings.py` testleri (T-307 FAZ 2, KURAL 3).

`~/.ensemble/ayarlar.json` — dosya izni 0600, atomik yazma, bozuk/eksik
dosyada fail-safe (boş sözlük, açılışı ENGELLEMEZ).
"""

import json
import stat
import sys

import pytest

from ensemble.store.provider_settings import (
    read_provider_settings,
    settings_path,
    write_provider_settings,
)


def test_settings_path_base_dir_ile_ayrisir(tmp_path):
    assert settings_path(tmp_path) == tmp_path / ".ensemble" / "ayarlar.json"


def test_dosya_yoksa_bos_sozluk_doner(tmp_path):
    assert read_provider_settings(tmp_path) == {}


def test_yaz_sonra_oku_ayni_veriyi_doner(tmp_path):
    write_provider_settings({"llm_provider": "gemini", "gemini_api_key": "k"}, tmp_path)
    assert read_provider_settings(tmp_path) == {"llm_provider": "gemini", "gemini_api_key": "k"}


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX izin biti — Windows'ta anlamsız")
def test_dosya_izni_0600(tmp_path):
    write_provider_settings({"llm_provider": "gemini"}, tmp_path)
    mode = stat.S_IMODE(settings_path(tmp_path).stat().st_mode)
    assert mode == 0o600, f"beklenen 0600, gerçek {oct(mode)}"


def test_ikinci_yazma_ilkini_TAMAMEN_degistirir_birlestirmez(tmp_path):
    write_provider_settings({"llm_provider": "gemini", "gemini_api_key": "k1"}, tmp_path)
    write_provider_settings({"llm_provider": "ollama"}, tmp_path)
    assert read_provider_settings(tmp_path) == {"llm_provider": "ollama"}


def test_bozuk_json_bos_sozluk_doner_acilis_ENGELLENMEZ(tmp_path):
    path = settings_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("{ bozuk json", encoding="utf-8")
    assert read_provider_settings(tmp_path) == {}


def test_dosya_ozeti_json_nesnesi_degilse_bos_sozluk_doner(tmp_path):
    path = settings_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    assert read_provider_settings(tmp_path) == {}


def test_dizin_yoksa_kendisi_olusturulur(tmp_path):
    base = tmp_path / "yeni-ev-dizini"
    assert not base.exists()
    write_provider_settings({"llm_provider": "gemini"}, base)
    assert read_provider_settings(base) == {"llm_provider": "gemini"}


def test_gecici_tmp_dosya_yazma_sonrasi_kalmaz(tmp_path):
    write_provider_settings({"llm_provider": "gemini"}, tmp_path)
    kalanlar = {p.name for p in (tmp_path / ".ensemble").iterdir()}
    assert kalanlar == {"ayarlar.json"}, f"tmp dosya temizlenmemiş: {kalanlar}"
