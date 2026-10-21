# ===================================================
# Gehihi Server - Dockerfile cho Render.com & Production
# Tích hợp Web Dashboard (Tiếng Việt) + Dynamic Engine (OTA & WebSocket)
# ===================================================

# Runtime Container (Debian Bookworm với Python 3.11, Nginx, FFmpeg, Libopus đầy đủ)
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

# Sao chép Frontend Web Admin Dashboard (Giao diện Tiếng Việt hoàn chỉnh clone từ Web_templates)
COPY main/web_admin /usr/share/nginx/html

# Sao chép Dynamic Backend (OTA + WebSocket + REST APIs)
COPY main/dynamic_server.py /app/dynamic_server.py
COPY main/web_admin /app/web_admin

# Sao chép và cấp quyền script khởi động
COPY docs/docker/start.sh /start.sh
RUN chmod +x /start.sh

# Cổng mặc định (Render sẽ inject $PORT động)
EXPOSE 8002

CMD ["/start.sh"]
