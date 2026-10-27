# Máy Chủ Trợ Lý AI Xiaozhi (Xiaozhi Server Go - Phiên Bản Tiếng Việt)

Dự án máy chủ trợ lý thông minh đa phương thức mã nguồn mở hiệu năng cao viết bằng **Go (Golang)**, được bản địa hóa **100% Tiếng Việt** và tối ưu hóa sẵn sàng triển khai trên nền tảng **Render (Cloud)** và kết nối với dòng robot **Xiaozhi ESP32**.

- **URL Dashboard trên Render:** [https://gehihi.onrender.com/](https://gehihi.onrender.com/)
- **Mã nguồn GitHub:** [https://github.com/meeyzinh/gehihi](https://github.com/meeyzinh/gehihi)
- **Địa chỉ OTA cho Robot ESP32:** `https://gehihi.onrender.com/api/ota/`
- **Địa chỉ WebSocket (WSS):** `wss://gehihi.onrender.com/ws`

---

## 🌟 Tính Năng Nổi Bật

1. **Giao diện Quản trị Tiếng Việt:** Toàn bộ bảng điều khiển Web Dashboard, mẫu nhân vật, trợ lý AI, thông báo, nhật ký cấu hình đều là Tiếng Việt chuẩn mực.
2. **Hỗ trợ Triển khai Render (Single-Port Cloud):** Tích hợp thông minh WebSocket và HTTP Web Dashboard trên cùng 1 cổng duy nhất do Render cấp phát qua biến môi trường `$PORT`, hỗ trợ tự động định tuyến SSL/TLS (HTTPS/WSS).
3. **Kết nối Realtime Voice AI:** Đàm thoại hai chiều full-duplex thời gian thực với Robot Xiaozhi ESP32 qua giao thức WebSocket bảo mật, hỗ trợ mã hóa Opus và PCM.
4. **Hỗ trợ Đa Nhà Cung Cấp (Providers):**
   - **ASR (Nhận dạng giọng nói):** Volcengine Doubao, Deepgram, GoSherpa, iFlytek, StepFun...
   - **LLM (Mô hình ngôn ngữ):** OpenAI tương thích (GPT-4o, Claude, DeepSeek, Qwen...), Ollama (mô hình nội bộ), Doubao Ark, Coze...
   - **TTS (Tổng hợp giọng nói):** Microsoft EdgeTTS (giọng Việt Nam: `vi-VN-HoaiMyNeural`, `vi-VN-NamMinhNeural`), Doubao TTS, Deepgram...
   - **VLLM (Thị giác AI):** Nhận diện hình ảnh qua camera ESP32.
5. **OTA Tự Động:** Quản lý và nâng cấp firmware không dây từ xa cho các robot Xiaozhi.
6. **Múi Giờ Chuẩn Việt Nam:** Đồng bộ hóa thời gian máy chủ theo múi giờ UTC+7 (+420 phút).

---

## 🚀 Hướng Dẫn Triển Khai Lên Render

### Cách 1: Triển khai qua Dockerfile (Khuyên dùng)
Dự án đã tích hợp sẵn `Dockerfile` đa giai đoạn (Multi-stage build) và tệp `render.yaml`:
1. Đăng nhập vào [Render.com](https://render.com).
2. Tạo mới một **Web Service**, liên kết với kho lưu trữ GitHub `https://github.com/meeyzinh/gehihi`.
3. Trong phần cấu hình Service:
   - **Environment:** Docker
   - **Region:** Singapore (để có độ trễ thấp nhất về Việt Nam)
   - **Branch:** `main`
4. Cấu hình các biến môi trường (Environment Variables):
   - `PORT`: `10000` (Render tự động cấp hoặc bạn đặt mặc định)
   - `WEBSOCKET_URL`: `wss://gehihi.onrender.com/ws`
   - `TIMEZONE_OFFSET`: `420` (Múi giờ Việt Nam UTC+7)
   - `TZ`: `Asia/Ho_Chi_Minh`
5. Bấm **Create Web Service**. Sau khi quá trình build hoàn tất, truy cập `https://gehihi.onrender.com/`.

---

## 🤖 Hướng Dẫn Kết Nối Robot Xiaozhi ESP32

### Cách 1: Thiết lập qua giao diện Wi-Fi của Robot (Không cần nạp lại code)
1. Bấm giữ nút cấu hình trên Robot Xiaozhi để đưa robot vào chế độ phát Wi-Fi (AP mode).
2. Dùng điện thoại hoặc máy tính kết nối vào mạng Wi-Fi của Robot (thường có tên dạng `Xiaozhi-XXXX`).
3. Mở trình duyệt truy cập địa chỉ cấu hình (mặc định: `192.168.4.1`).
4. Nhập tên Wi-Fi và Mật khẩu nhà bạn.
5. Tại mục **OTA URL**, nhập:
   ```text
   https://gehihi.onrender.com/api/ota/
   ```
6. Bấm Lưu và khởi động lại robot.

### Cách 2: Nạp sẵn Firmware từ mã nguồn `xiaozhi-esp32`
Trong thư mục `xiaozhi-esp32-main`:
1. Tệp `main/Kconfig.projbuild` và `sdkconfig.defaults` đã được cấu hình mặc định:
   ```ini
   CONFIG_OTA_URL="https://gehihi.onrender.com/api/ota/"
   CONFIG_LANGUAGE_VI_VN=y
   ```
2. Dùng ESP-IDF để biên dịch và nạp vào mạch:
   ```bash
   idf.py set-target esp32s3
   idf.py build
   idf.py -p COMx flash monitor
   ```

---

## 🔑 Đăng Nhập & Kích Hoạt Robot Trên Dashboard

1. Mở trang quản trị: `https://gehihi.onrender.com/`
2. Đăng nhập bằng tài khoản:
   - **Tên đăng nhập:** `admin`
   - **Mật khẩu ban đầu:** `123456` (hoặc mật khẩu tạm thời được in trong tab Logs của Render khi khởi động lần đầu). Vui lòng đổi mật khẩu tại trang *Cài đặt cá nhân*.
3. Vào trang **Nhà cung cấp AI**: Nhập API Key cho OpenAI hoặc Doubao/Ollama và EdgeTTS.
4. Khi robot khởi động và kết nối Wi-Fi, robot sẽ tự động liên hệ tới server và phát ra **mã kích hoạt 6 chữ số**.
5. Trên Dashboard, vào mục **Trợ lý AI** -> Bấm **Thêm thiết bị** -> Nhập địa chỉ MAC hoặc mã xác thực để liên kết robot.
6. Bắt đầu trò chuyện bằng giọng nói Tiếng Việt với robot!
