"""Yerel sağlayıcı ayarları — dosya tabanlı depo (T-307 FAZ 2, KURAL 3).

`~/.ensemble/ayarlar.json`, dosya izni `0600` (yalnız sahibi okur/yazar).

Neden DB DEĞİL: DB (`store/*.py`) `.harness/` ile aynı ruhtaki bir
PROJEKSİYONDUR — `make rebuild` onu yeniden kurar, konteyner/paket
yeniden yaratılınca kaybolması BEKLENEN bir davranıştır (D-39). Bir API
anahtarı orada YANLIŞ yerde durur: `make rebuild` koşan biri anahtarını
kaybettiğini fark etmeden yeni bir Gemini/Groq çağrısı Fake adaptere
sessizce düşebilirdi. Bu dosya BİLEREK DB'nin ve git'in (repo) dışında,
kullanıcının kendi ev dizininde yaşar — ne commit'lenir ne de `make rebuild`
onu siler.

Neden repo'da DEĞİL: `.gitignore`'a güvenmek tek katmanlı bir savunmadır
(bir geliştirici `git add -f` yapabilir). Repo AĞACININ dışında bir yol
kullanmak (`Path.home()`), anahtarın hiçbir zaman `git status`/`git diff`
çıktısında GÖRÜNMEMESİNİ garantiler — ikinci, yapısal bir katman.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from threading import Lock

_DIRNAME = ".ensemble"
_FILENAME = "ayarlar.json"

# Aynı süreç içinde eşzamanlı iki PUT isteği (nadir ama olanaklı — uvicorn
# birden çok thread'de istek işleyebilir) yazma sırasında birbirinin
# içeriğini SESSİZCE ezmemeli (oku-değiştir-yaz döngüsü tek kilit altında).
_write_lock = Lock()

# Yalnızca sahibi okur/yazar — grup/diğerleri erişemez (KURAL 3).
_OWNER_READ_WRITE = stat.S_IRUSR | stat.S_IWUSR


def settings_path(base_dir: str | os.PathLike[str] | None = None) -> Path:
    """`ayarlar.json`'un TAM yolu. `base_dir` yalnız TESTLER için — üretim
    kodu her zaman `base_dir=None` ile çağırır ve gerçek `Path.home()`'u
    kullanır (`HOME` ortam değişkenine saygılıdır — Docker/paket kurulumu
    `HOME`'u değiştirerek bu yolu taşınabilir kılabilir, ayrıca bir
    `ENSEMBLE_*` ayarı İCAT ETMEDEN)."""
    base = Path(base_dir) if base_dir is not None else Path.home()
    return base / _DIRNAME / _FILENAME


def read_provider_settings(base_dir: str | os.PathLike[str] | None = None) -> dict:
    """Kaydedilmiş ayarları döner; dosya yoksa ya da okunamıyorsa (bozuk JSON,
    izin hatası) BOŞ sözlük döner — bu bir "henüz hiç kaydedilmedi" ile
    ayırt edilemez, ki bu FAIL-SAFE'dir: bozuk bir dosya açılışı ENGELLEMEZ,
    yalnızca overlay'i uygulamaz (env/varsayılan değerler geçerli kalır)."""
    path = settings_path(base_dir)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_provider_settings(data: dict, base_dir: str | os.PathLike[str] | None = None) -> None:
    """`data`'yı `ayarlar.json`'a ATOMİK olarak yazar (tmp dosya + `rename`) —
    yazma yarıda kesilirse (süreç öldürülürse) dosya ya ESKİ ya da TAMAMEN
    YENİ içerikle kalır, hiçbir zaman yarım/bozuk JSON'da takılı kalmaz.
    `os.chmod` HEM tmp dosyaya HEM son dosyaya uygulanır (POSIX'te `rename`
    tmp'nin izinlerini korur, ama bu çift-uygulama platformlar arası daha
    savunmacı — Windows'ta chmod'un etkisi sınırlıdır, best-effort)."""
    with _write_lock:
        path = settings_path(base_dir)
        directory = path.parent
        directory.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(tmp_path, _OWNER_READ_WRITE)
        tmp_path.replace(path)
        os.chmod(path, _OWNER_READ_WRITE)
