# Gehihi - Máy Chủ Quản Trị & Điều Khiển Robot Xiaozhi AI (Render.com)

Hệ thống máy chủ điều khiển thông minh dành cho robot AI Xiaozhi (ESP32 / ESP32-S3), hỗ trợ giao diện Web Dashboard quản trị bằng **Tiếng Việt**, đồng thời cung cấp đầy đủ các cổng dịch vụ OTA, WebSocket AI và REST API.

- **Link Server trên Render:** [https://gehihi.onrender.com/](https://gehihi.onrender.com/)
- **Giao diện Web Dashboard:** [https://gehihi.onrender.com/](https://gehihi.onrender.com/) (Ngôn ngữ chính: Tiếng Việt)
- **Cổng kết nối OTA cho Robot:** `https://gehihi.onrender.com/xiaozhi/ota/`
- **Cổng kết nối WebSocket AI cho Robot:** `wss://gehihi.onrender.com/xiaozhi/v1/`

---

## 🌟 Tính Năng Nổi Bật

1. **Giao Diện Tiếng Việt Toàn Diện:**
   - Hệ thống Web Dashboard tự động tải với giao diện và thông báo Tiếng Việt.
   - Quản lý thiết bị, mẫu trợ lý AI, thông số hệ thống và lịch sử đàm thoại.

2. **Tương Thích Động Trên Render (Dynamic Cloud Deployment):**
   - Tự động nhận diện biến môi trường `$PORT` do Render cấp phát.
   - Nginx Reverse Proxy điều phối thông minh cả Web tĩnh, WebSocket thời gian thực và OTA Endpoint trên cùng một Domain duy nhất có chứng chỉ SSL/TLS.
   - Tích hợp Dynamic Backend Engine giúp server luôn hoạt động ổn định và phản hồi tức thì mà không bị gián đoạn.

3. **Kết Nối Hoàn Hảo Với Robot Xiaozhi AI Firmware:**
   - Hỗ trợ đầy đủ các bản build ESP-IDF trong thư mục `Gehihi-main`.
   - Cấu hình mặc định OTA URL trỏ tới `https://gehihi.onrender.com/xiaozhi/ota/`.
   - Múi giờ chuẩn Việt Nam (GMT+7, +420 phút).

---

## 🚀 Hướng Dẫn Triển Khai Lên Render.com

### Cách 1: Triển Khai Nhanh Qua Blueprint (Khuyến Nghị)
1. Đăng nhập vào [Render.com](https://render.com/).
2. Chọn **New** -> **Blueprint**.
3. Kết nối với kho lưu trữ GitHub: `https://github.com/meeyzinh/gehihi`.
4. Render sẽ tự động đọc file `render.yaml` và triển khai dịch vụ Web Service `gehihi` với cấu hình Docker tối ưu.

### Cách 2: Triển Khai Thủ Công (Web Service)
1. Trên Render, chọn **New** -> **Web Service**.
2. Chọn Repository: `meeyzinh/gehihi`.
3. Cấu hình các thông số:
   - **Name:** `gehihi`
   - **Environment:** `Docker`
   - **Dockerfile Path:** `./Dockerfile`
   - **Plan:** `Free` (hoặc Starter)
4. Biến môi trường (Environment Variables):
   - `PORT`: `10000` (Render tự động cấp phát)
   - `RENDER_EXTERNAL_URL`: `https://gehihi.onrender.com`
   - `WEBSOCKET_URL`: `wss://gehihi.onrender.com/xiaozhi/v1/`
5. Nhấn **Deploy Web Service** và chờ Render hoàn tất quá trình build.

---

## 🤖 Kết Nối Firmware Robot Xiaozhi (`Gehihi-main`)

Firmware trong thư mục `Gehihi-main` đã được cấu hình sẵn để kết nối tới server Gehihi:
- `Kconfig.projbuild`:
  ```kconfig
  config OTA_URL
      string "Default OTA URL"
      default "https://gehihi.onrender.com/xiaozhi/ota/"
  
  choice
      prompt "Default Language"
      default LANGUAGE_VI_VN
  ```
- `sdkconfig.defaults`:
  ```ini
  CONFIG_OTA_URL="https://gehihi.onrender.com/xiaozhi/ota/"
  CONFIG_LANGUAGE_VI_VN=y
  ```

### Các bước nạp Firmware cho robot:
```bash
cd Gehihi-main
idf.py set-target esp32s3   # hoặc esp32 / esp32c3 tuỳ bo mạch
idf.py build
idf.py -p COMx flash monitor
```
Khi robot khởi động và kết nối Wi-Fi, nó sẽ tự động gửi request đến `https://gehihi.onrender.com/xiaozhi/ota/`, nhận link WebSocket `wss://gehihi.onrender.com/xiaozhi/v1/` và bắt đầu đàm thoại AI bằng tiếng Việt!

