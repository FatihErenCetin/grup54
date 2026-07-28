#!/usr/bin/env bash
# Ensemble macOS masaüstü paketi — .app + .dmg üretir (T-305).
#
# Kullanım (repo kökünden):
#   packaging/build_macos.sh
# ya da:
#   make paket-macos
#
# Çıktı:
#   packaging/dist-macos/Ensemble.app   — çalıştırılabilir uygulama paketi
#   packaging/dist-macos/Ensemble.dmg   — sürükle-bırak kurulum imajı
#
# ÖN KOŞUL: bu yalnızca macOS'ta çalışır (hdiutil + .app/.dmg macOS'a özgü).
# Bağımlılıklar: uv (proje ortamı), node/npm (frontend build) — ikisi de
# geliştirme ortamında zaten var olmalı (bkz. AGENTS.md §Build/test).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGING_DIR="$REPO_ROOT/packaging"
FRONTEND_DIR="$REPO_ROOT/src/frontend"
DIST_DIR="$PACKAGING_DIR/dist-macos"
BUILD_DIR="$PACKAGING_DIR/build-macos"
APP_NAME="Ensemble"
# launcher.py::PREFERRED_PORT ile AYNI OLMAK ZORUNDA — frontend build-time'da
# bu porta karşı derlenir, launcher runtime'da backend'i bu porta bağlar.
BACKEND_PORT=8756

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "HATA: bu script yalnızca macOS'ta çalışır (.app/.dmg macOS'a özgü)." >&2
  exit 1
fi

echo "== 1/4: Frontend production build (VITE_API_BASE_URL=http://127.0.0.1:${BACKEND_PORT}) =="
if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo "   node_modules yok — npm ci çalıştırılıyor..."
  (cd "$FRONTEND_DIR" && npm ci)
fi
(
  cd "$FRONTEND_DIR"
  # VITE_MOCK boş bırakılır (#188 prod hijyen kuralı — mock fixture'ları
  # dist'e sızmasın). VITE_API_BASE_URL sabit portu JS'e gömer — Vite ortam
  # değişkenlerini DERLEME ANINDA statik olarak inline eder, runtime'da
  # değiştirilemez (bkz. packaging/launcher.py PREFERRED_PORT yorumu).
  VITE_API_BASE_URL="http://127.0.0.1:${BACKEND_PORT}" VITE_MOCK= npm run build
)
if [[ ! -f "$FRONTEND_DIR/dist/index.html" ]]; then
  echo "HATA: frontend build dist/index.html üretmedi." >&2
  exit 1
fi

echo "== 2/4: PyInstaller — .app paketi =="
rm -rf "$DIST_DIR" "$BUILD_DIR"
mkdir -p "$DIST_DIR" "$BUILD_DIR"
(
  cd "$REPO_ROOT"
  uv run --with-requirements "$PACKAGING_DIR/requirements-build.txt" \
    pyinstaller "$PACKAGING_DIR/ensemble.spec" \
    --noconfirm \
    --distpath "$DIST_DIR" \
    --workpath "$BUILD_DIR"
)

APP_PATH="$DIST_DIR/Ensemble.app"
if [[ ! -d "$APP_PATH" ]]; then
  echo "HATA: PyInstaller Ensemble.app üretmedi ($APP_PATH yok)." >&2
  exit 1
fi
APP_SIZE=$(du -sh "$APP_PATH" | cut -f1)
echo "   Ensemble.app üretildi: $APP_PATH ($APP_SIZE)"

echo "== 3/4: .dmg — sürükle-bırak kurulum imajı =="
DMG_STAGE="$BUILD_DIR/dmg-stage"
rm -rf "$DMG_STAGE"
mkdir -p "$DMG_STAGE"
cp -R "$APP_PATH" "$DMG_STAGE/"
ln -s /Applications "$DMG_STAGE/Applications"
# İlk açılışta Gatekeeper uyarısı verir (imzasız/notarize edilmemiş paket —
# bkz. docs/macos-paket-kurulumu.md) — bunu GİZLEMİYORUZ, kısa bir not dosyası
# dmg'nin içine koyuyoruz ki kullanıcı .app'i kopyalamadan önce görsün.
cat > "$DMG_STAGE/İlk açılışta - ÖNEMLİ.txt" <<'EOF'
Bu uygulama Apple tarafından imzalanmamıştır (Apple Developer hesabı
gerektirir; bu proje bir hesap satın almadı).

İlk açılışta macOS Gatekeeper "bilinmeyen geliştirici" uyarısı verecek ve
normal çift tıklama ile açılmayacaktır. Açmak için:

  1. Ensemble.app'i Applications'a sürükleyin (bu pencerede zaten var).
  2. Applications'ta Ensemble.app'e SAĞ TIKLAYIN → "Aç" seçin.
  3. Çıkan uyarı penceresinde tekrar "Aç"a tıklayın.

Bu yalnızca İLK açılışta gerekir. Sonraki açılışlar normal çift tıklamayla
çalışır.

Detay + veri dizini + kaldırma: docs/macos-paket-kurulumu.md (proje reposu).
EOF

DMG_PATH="$DIST_DIR/${APP_NAME}.dmg"
rm -f "$DMG_PATH"
TMP_DMG="$BUILD_DIR/${APP_NAME}-tmp.dmg"
rm -f "$TMP_DMG"
hdiutil create -volname "$APP_NAME" -srcfolder "$DMG_STAGE" -ov -format UDRW "$TMP_DMG" >/dev/null
hdiutil convert "$TMP_DMG" -format UDZO -o "$DMG_PATH" -ov >/dev/null
rm -f "$TMP_DMG"

if [[ ! -f "$DMG_PATH" ]]; then
  echo "HATA: .dmg üretilemedi ($DMG_PATH yok)." >&2
  exit 1
fi
DMG_SIZE=$(du -sh "$DMG_PATH" | cut -f1)

echo "== 4/4: Özet =="
echo "   .app : $APP_PATH ($APP_SIZE)"
echo "   .dmg : $DMG_PATH ($DMG_SIZE)"
echo ""
echo "   Kurulum notu (Gatekeeper dahil): docs/macos-paket-kurulumu.md"
