# syntax=docker/dockerfile:1
#
# Ensemble frontend — yerel TEK-KOMUT kurulumu (T-307 FAZ 1) için geliştirme
# sunucusu imajı. Prod build/deploy Vercel'de yapılır (`vercel.json`,
# `frontend-build-guard` — bu Dockerfile ONLARI DEĞİŞTİRMEZ/YERİNE GEÇMEZ);
# burası yalnızca PO'nun kendi makinesinde `docker compose up` ile tek
# komutla açılan bir arayüz içindir.
FROM node:22-slim

WORKDIR /app

# --- Katman 1: yalnızca bağımlılık grafiği (kaynak kodu HENÜZ yok) ---
# Kaynak değiştiğinde (bağımlılıklar değişmediğinde) `npm ci` yeniden
# koşmaz — Docker layer cache'i korunur (kök Dockerfile'daki `uv sync`
# katmanlama ilkesiyle AYNI).
COPY package.json package-lock.json ./
RUN npm ci

# --- Katman 2: kaynak kodu ---
COPY . .

EXPOSE 5173

# `--host 0.0.0.0` ZORUNLU: Vite varsayılan olarak yalnız loopback'e
# (127.0.0.1) bağlanır — konteyner İÇİNDEN bu, host makineden HİÇ
# erişilemez demektir (`localhost:5173` bağlantı reddeder).
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
