#!/bin/bash
set -e

# Đọc cổng do Render hoặc Docker cấp phát qua biến môi trường PORT (mặc định 8002)
PORT="${PORT:-8002}"

echo "======================================================="
echo "  [Gehihi Server] Khởi động trên cổng: $PORT"
echo "  Domain công khai: ${RENDER_EXTERNAL_URL:-https://gehihi.onrender.com}"
echo "  OTA Endpoint:     ${RENDER_EXTERNAL_URL:-https://gehihi.onrender.com}/xiaozhi/ota/"
echo "  WebSocket URL:    wss://gehihi.onrender.com/xiaozhi/v1/"
echo "======================================================="

# Tự động thay thế listen port trong Nginx config bằng $PORT
sed -i "s/listen  8002;/listen ${PORT};/g" /etc/nginx/nginx.conf || true
sed -i "s/listen 8002;/listen ${PORT};/g" /etc/nginx/nginx.conf || true

# Khởi động Dynamic Server (OTA + WebSocket + Fallback Dashboard API)
if [ -f "/app/dynamic_server.py" ]; then
    (while true; do python3 /app/dynamic_server.py; sleep 2; done) &
    echo "[Gehihi Server] Dynamic Engine đã khởi động nền trên port 8003 (HTTP/OTA) và 8000 (WS)."
fi

# Nếu có cấu hình MySQL và có file jar, khởi động Spring Boot API
if [ -n "$SPRING_DATASOURCE_DRUID_URL" ] && [ -f "/app/xiaozhi-esp32-api.jar" ]; then
    echo "[Gehihi Server] Phát hiện cấu hình MySQL. Đang khởi chạy Spring Boot manager-api..."
    java -jar /app/xiaozhi-esp32-api.jar \
      --server.port=8004 \
      --spring.datasource.druid.url=${SPRING_DATASOURCE_DRUID_URL} \
      --spring.datasource.druid.username=${SPRING_DATASOURCE_DRUID_USERNAME} \
      --spring.datasource.druid.password=${SPRING_DATASOURCE_DRUID_PASSWORD} \
      --spring.data.redis.host=${SPRING_DATA_REDIS_HOST:-127.0.0.1} \
      --spring.data.redis.password=${SPRING_DATA_REDIS_PASSWORD:-} \
      --spring.data.redis.port=${SPRING_DATA_REDIS_PORT:-6379} &
fi

# Khởi động Nginx ở chế độ foreground
echo "[Gehihi Server] Khởi động Nginx..."
exec nginx -g 'daemon off;'