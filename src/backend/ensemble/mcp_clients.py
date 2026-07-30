"""AI aracı başına MCP bağlanma reçetesi (#332).

NEDEN AYRI MODÜL: Ensemble'ın vaadi "**herkesin** aracı aynı paylaşılan bağlamı
okur" — ama 29 Tem ölçümünde ayarlar sayfası birebir "Claude Code'a bağlan"
diyordu ve tek bir yol (`<repo>/.mcp.json`) üretiyordu. Sunucunun kendisi zaten
araç-bağımsız (standart `mcpServers` şeması, stdio); eksik olan **araç başına
doğru dosya yolu + biçim**. Bu tablo o eksiği kapatır ve tek yerde yaşar —
router, `make mcp` belgesi ve AGENTS.md aynı kaynaktan beslenir (drift yok).

BİÇİM AYRIMI (bu işin can alıcı noktası): dört araç JSON + `mcpServers`
konuşur, **Codex CLI TOML + `[mcp_servers.<ad>]`** konuşur. Aynı JSON gövdesini
Codex'e vermek sessizce çalışmaz — bu yüzden `bicim` alanı var ve testte
`tomllib`/`json` ile GERÇEKTEN parse edilerek kilitlenir.

YOLLAR DOĞRULANDI (30 Tem 2026, resmî belgeden — ezberden YAZILMADI):
  - Claude Code  `<repo>/.mcp.json`               https://code.claude.com/docs/en/mcp
  - Cursor       `<repo>/.cursor/mcp.json`        https://cursor.com/docs/context/mcp
  - Gemini CLI   `<repo>/.gemini/settings.json`   https://google-gemini.github.io/gemini-cli/docs/tools/mcp-server.html
  - Kiro         `<repo>/.kiro/settings/mcp.json` https://kiro.dev/docs/mcp/configuration/
  - Codex CLI    `~/.codex/config.toml`           https://developers.openai.com/codex/mcp

Doğrulayamadığım hiçbir araç bu listede YOK (yanlış yol yazmak, hiç yazmamaktan
kötüdür — kullanıcı dosyayı oluşturur, araç okumaz, sebebini bulamaz).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

#: MCP sunucusunun config içindeki adı — araçlar bunu tool ön-eki yapar
#: (ör. Claude Code'da `mcp__ensemble__who_is_touching`).
SUNUCU_ADI = "ensemble"

#: Hosted'da repo kökü BİLİNEMEZ (sunucunun diski kullanıcının diski değil) —
#: mutlak yol yerine bu yer tutucu basılır. Sunucunun kendi dosya yolunu
#: hosted'da ifşa ETMEMEK ayrıca bir gereklilik (settings.py KURAL 1'in ruhu).
YER_TUTUCU_REPO = "<repo-koku>"


@dataclass(frozen=True)
class AracRecetesi:
    """Tek bir AI aracının bağlanma reçetesi."""

    arac: str
    """Slug (frontend seçim anahtarı) — ör. `claude-code`."""
    ad: str
    """İnsan adı — ör. `Claude Code`."""
    bicim: Literal["json", "toml"]
    """Dosya biçimi. Codex TOML, diğerleri JSON."""
    yol_sablonu: str
    """`{repo}` yer tutucusu içeren hedef yol."""
    paylasimli_dosya: bool
    """True = bu dosya MCP DIŞI ayarlar da barındırır (Gemini CLI settings.json,
    Codex config.toml). Üzerine yazmak diğer ayarları siler → kullanıcıya
    "birleştir" uyarısı gösterilir. False = dosya yalnız MCP sunucularını tutar
    (yine de başka sunucu tanımlı olabilir; genel "varsa birleştir" uyarısı
    UI'da her araç için ayrıca durur)."""
    aciklama_sablonu: str
    """Araca özel adım (yeniden başlatma, CLI kısayolu vb.); `{repo}` içerebilir."""
    kaynak: str
    """Yolun doğrulandığı resmî belge — "uydurmadık"ın kanıtı."""

    def yol(self, repo_koku: str) -> str:
        return self.yol_sablonu.format(repo=repo_koku)

    def aciklama(self, repo_koku: str) -> str:
        return self.aciklama_sablonu.format(repo=repo_koku)


ARACLAR: tuple[AracRecetesi, ...] = (
    AracRecetesi(
        arac="claude-code",
        ad="Claude Code",
        bicim="json",
        yol_sablonu="{repo}/.mcp.json",
        paylasimli_dosya=False,
        aciklama_sablonu=(
            "Proje kapsamlı dosya. Yapıştırdıktan sonra Claude Code'u YENİDEN "
            "BAŞLAT; ilk açılışta proje sunucusunu onaylaman istenir. CLI "
            "kısayolu: `claude mcp add ensemble -- uv run --directory {repo} "
            "python -m ensemble_mcp.server`"
        ),
        kaynak="https://code.claude.com/docs/en/mcp",
    ),
    AracRecetesi(
        arac="cursor",
        ad="Cursor",
        bicim="json",
        yol_sablonu="{repo}/.cursor/mcp.json",
        paylasimli_dosya=False,
        aciklama_sablonu=(
            "Proje kapsamlı dosya (`.cursor/` klasörünü sen oluşturursun). "
            "Tüm projelerde açık olsun istersen aynı içerik `~/.cursor/mcp.json`'a "
            "gider. Settings > MCP panelinden sunucunun yeşil olduğunu doğrula."
        ),
        kaynak="https://cursor.com/docs/context/mcp",
    ),
    AracRecetesi(
        arac="codex",
        ad="Codex CLI",
        bicim="toml",
        yol_sablonu="~/.codex/config.toml",
        paylasimli_dosya=True,
        aciklama_sablonu=(
            "Codex JSON DEĞİL **TOML** okur — diğer araçların parçacığını buraya "
            "yapıştırmak çalışmaz. Dosyada başka ayarların da var: üzerine yazma, "
            "sona EKLE. CLI kısayolu: `codex mcp add ensemble -- uv run "
            "--directory {repo} python -m ensemble_mcp.server`"
        ),
        kaynak="https://developers.openai.com/codex/mcp",
    ),
    AracRecetesi(
        arac="gemini-cli",
        ad="Gemini CLI",
        bicim="json",
        yol_sablonu="{repo}/.gemini/settings.json",
        paylasimli_dosya=True,
        aciklama_sablonu=(
            "Bu dosya Gemini CLI'ın GENEL ayar dosyası (tema, araçlar, …) — "
            "üzerine yazma, yalnız `mcpServers` anahtarını mevcut nesneye EKLE. "
            "Tüm projeler için: `~/.gemini/settings.json`. Doğrulama: oturumda "
            "`/mcp` yaz."
        ),
        kaynak="https://google-gemini.github.io/gemini-cli/docs/tools/mcp-server.html",
    ),
    AracRecetesi(
        arac="kiro",
        ad="Kiro",
        bicim="json",
        yol_sablonu="{repo}/.kiro/settings/mcp.json",
        paylasimli_dosya=False,
        aciklama_sablonu=(
            "Çalışma-alanı (workspace) kapsamı. Tüm projeler için: "
            "`~/.kiro/settings/mcp.json` — ikisi de varsa workspace kazanır. "
            "Kiro dosyayı kaydedince sunucuyu kendiliğinden yeniden bağlar."
        ),
        kaynak="https://kiro.dev/docs/mcp/configuration/",
    ),
)


def stdio_komutu(repo_koku: str) -> tuple[str, list[str]]:
    """Beş aracın da çalıştırdığı TEK komut — `uv run --directory <repo>`.

    `--directory` şart: araç MCP sunucusunu kendi cwd'sinden başlatır, oysa
    `ensemble_mcp` reponun uv workspace'inde yaşar.
    """
    return "uv", ["run", "--directory", repo_koku, "python", "-m", "ensemble_mcp.server"]


def _json_config(repo_koku: str) -> str:
    komut, args = stdio_komutu(repo_koku)
    return json.dumps(
        {"mcpServers": {SUNUCU_ADI: {"command": komut, "args": args}}},
        indent=2,
        ensure_ascii=False,
    )


def _toml_config(repo_koku: str) -> str:
    """Codex TOML'u.

    Dize kaçışı için `json.dumps` kullanılıyor: TOML "basic string" kaçış
    kuralları (`\\"`, `\\\\`, `\\n`, `\\uXXXX`) JSON'ınkinin üst kümesi, ve TOML
    dizi söz dizimi de JSON dizisiyle aynı — yani `json.dumps` çıktısı geçerli
    TOML üretir. Elle tırnak birleştirmek boşluklu/ters-bölülü Windows yollarında
    sessizce bozuk config üretirdi. `ensure_ascii=True` (varsayılan): Türkçe
    karakterli bir yolda bile ASCII-güvenli kaçış.
    """
    komut, args = stdio_komutu(repo_koku)
    return (
        f"[mcp_servers.{SUNUCU_ADI}]\n"
        f"command = {json.dumps(komut)}\n"
        f"args = {json.dumps(args)}\n"
    )


def config_metni(recete: AracRecetesi, repo_koku: str) -> str:
    """Reçetenin biçimine göre yapıştırılacak metni üretir."""
    if recete.bicim == "toml":
        return _toml_config(repo_koku)
    return _json_config(repo_koku)


def recete_bul(arac: str) -> AracRecetesi | None:
    return next((r for r in ARACLAR if r.arac == arac), None)
