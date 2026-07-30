"""`.gitignore` deseni SYMLINK'i de elemeli (#322 rebase artigi dersi).

OLCULEN OLAY (30 Tem 2026): #322'nin rebase'i sirasinda worktree'de frontend
testlerini kosturmak icin `node_modules` bir SYMLINK olarak kuruldu
(`ln -s /Users/<isim>/Developer/grup54/src/frontend/node_modules`), ardindan
`git add -A` onu REPOYA EKLEDI (mode 120000, hedefi kisisel makineye bagli
MUTLAK yol). CI yesil kaldi — hicbir test bu sinifi sormuyordu; hatayi review
yakaladi (Semih).

KOK NEDEN, tek karakter: `.gitignore`'da desen `node_modules/` idi.
Sondaki `/` git'e "YALNIZ DIZIN" der. `node_modules` adinda bir symlink git
icin dizin DEGILDIR -> desen onu KACIRIR. Yani ignore kurali vardi ve
calisiyordu; sadece bu bir vakayi kapsamiyordu.

Bu dosya iki ayri seyi kilitler:
  1. Depoda hic symlink OLMAMASI (belirti)
  2. Desenin symlink'i GERCEKTEN elemesi (kok neden)
Yalniz (1) yazilsaydi, biri deseni geri `/`'li hale getirdiginde test yesil
kalir ve kapi sessizce yeniden acilirdi.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent


def _git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=cwd or REPO_ROOT, capture_output=True, text=True, check=False
    )


def test_depoda_HIC_symlink_yok():
    """Belirti kilidi: izlenen agacta mode 120000 girdi olmamali.

    Kisisel makineye bagli mutlak yollu bir symlink baska bir gelistiricide
    kirik dosya olur; CI'da (node_modules zaten kuruluyken) fark edilmez.
    """
    sonuc = _git("ls-tree", "-r", "HEAD", "--full-tree")
    assert sonuc.returncode == 0, sonuc.stderr
    symlinkler = [
        satir.split("\t", 1)[1]
        for satir in sonuc.stdout.splitlines()
        if satir.startswith("120000 ")
    ]
    assert symlinkler == [], f"depoda symlink var: {symlinkler}"


def test_gitignore_deseni_SYMLINKI_de_eler(tmp_path):
    """Kok-neden kilidi — GERCEK git davranisiyla olculur, dizgiyle degil.

    Depodaki `.gitignore` gecici bir depoya kopyalanir, `node_modules` adinda
    bir SYMLINK kurulur ve `git status`'a bakilir. Iddia edilen sey degil,
    git'in NE YAPTIGI olculuyor.

    MUTASYON KILIDI: `.gitignore`'daki `node_modules` desenine sondaki `/`
    geri eklenirse -> symlink stage'e girer, bu test kirilir.
    """
    (tmp_path / "src" / "frontend").mkdir(parents=True)
    (tmp_path / ".gitignore").write_text(
        (REPO_ROOT / ".gitignore").read_text(encoding="utf-8"), encoding="utf-8"
    )
    _git("init", "-q", ".", cwd=tmp_path)
    (tmp_path / "src" / "frontend" / "node_modules").symlink_to("/tmp/sahte-hedef")

    _git("add", "-A", cwd=tmp_path)
    izlenen = _git("ls-files", cwd=tmp_path).stdout.splitlines()

    assert "src/frontend/node_modules" not in izlenen, (
        "`node_modules` SYMLINK'i stage'e girdi — desen sondaki `/` yuzunden "
        "yalniz dizinleri eliyor olabilir (#322 artigi bu delikten gecti)"
    )


def test_gitignore_deseni_GERCEK_dosyalari_ELEMEZ(tmp_path):
    """Simetrik kilit: cozum asiri elemeye kaymasin.

    `node_modules` (slash'siz) desenin YOLUN HERHANGI bir yerinde eslesmesine
    yol acar; `src/frontend/src/app.ts` gibi normal dosyalar etkilenmemeli.
    """
    (tmp_path / "src" / "frontend" / "src").mkdir(parents=True)
    (tmp_path / ".gitignore").write_text(
        (REPO_ROOT / ".gitignore").read_text(encoding="utf-8"), encoding="utf-8"
    )
    _git("init", "-q", ".", cwd=tmp_path)
    (tmp_path / "src" / "frontend" / "src" / "app.ts").write_text("x", encoding="utf-8")

    _git("add", "-A", cwd=tmp_path)
    izlenen = _git("ls-files", cwd=tmp_path).stdout.splitlines()

    assert "src/frontend/src/app.ts" in izlenen, f"gercek dosya elendi: {izlenen}"
