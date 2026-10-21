# ===================================================
# Gehihi Server - Dockerfile cho Render.com & Production
# Tích hợp Web Dashboard (Tiếng Việt) + Dynamic Engine (OTA & WebSocket)
# ===================================================

# Giai đoạn 1: Build Vue Web Dashboard (dùng node:18 Debian glibc tiêu chuẩn)
FROM node:18 AS web-builder
WORKDIR /app
ENV NODE_OPTIONS="--max-old-space-size=2048"

COPY main/manager-web/package*.json ./
RUN npm install

COPY main/manager-web .
RUN npm run build

# Giai đoạn 2: Runtime Container (Debian Bookworm với Python 3.11, Nginx, FFmpeg, Libopus đầy đủ)
FROM python:3.11-slim-bookworm

# Cài đặt Nginx, FFmpeg, Libopus
RUN apt-get update && apt-get install -y --no-install-recommends \
        nginx \
        bash \
        curl \
        ffmpeg \
        libopus0 \
        libopus-dev \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /run/nginx /var/log/nginx /var/tmp/nginx /etc/nginx/conf.d /app

# Cài đặt dependencies cho Dynamic Engine (Hỗ trợ AI Gemini, Groq, DeepSeek, OpenAI, EdgeTTS, Opus)
RUN pip install --no-cache-dir \
    aiohttp \
    websockets \
    pyjwt \
    "edge-tts>=7.3.1" \
    opuslib-next \
    requests

# Cấu hình Nginx
COPY docs/docker/nginx.conf /etc/nginx/nginx.conf

# Sao chép Frontend Web Dashboard đã build
COPY --from=web-builder /app/dist /usr/share/nginx/html

# Sao chép Dynamic Backend (OTA + WebSocket + Fallback Dashboard API)
COPY main/dynamic_server.py /app/dynamic_server.py

# Sao chép và cấp quyền script khởi động
COPY docs/docker/start.sh /start.sh
RUN chmod +x /start.sh

# Cổng mặc định (Render sẽ inject $PORT động)
EXPOSE 8002

CMD ["/start.sh"]
