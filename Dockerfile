# ========================================================
# Stage 1: Build the Go binary with CGO (for SQLite3)
# ========================================================
FROM golang:1.24-alpine AS builder

RUN apk add --no-cache gcc musl-dev sqlite-dev git build-base

WORKDIR /build

# Cache dependencies
COPY go.mod go.sum ./
RUN go mod download

# Copy source code
COPY . .

# Build statically linked binary with CGO enabled
RUN CGO_ENABLED=1 GOOS=linux go build -ldflags="-s -w -extldflags '-static'" -o xiaozhi-server ./src/main.go

# ========================================================
# Stage 2: Minimal runtime image
# ========================================================
FROM alpine:latest

RUN apk add --no-cache \
    ca-certificates \
    sqlite-libs \
    tzdata \
    procps

WORKDIR /app

# Copy binary & assets from builder
COPY --from=builder /build/xiaozhi-server /app/xiaozhi-server
COPY --from=builder /build/web /app/web
COPY --from=builder /build/config.yaml /app/config.yaml
COPY --from=builder /build/.config.yaml /app/.config.yaml
COPY --from=builder /build/music /app/music

# Ensure execution permission
RUN chmod +x /app/xiaozhi-server

# Set default timezone to Asia/Ho_Chi_Minh (UTC+7)
ENV TZ=Asia/Ho_Chi_Minh
ENV PORT=8080
ENV WEBSOCKET_URL=wss://gehihi.onrender.com/ws
ENV TIMEZONE_OFFSET=420

EXPOSE 8080 8000

CMD ["./xiaozhi-server"]
