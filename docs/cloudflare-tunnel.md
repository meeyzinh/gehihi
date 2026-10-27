# Truy cập Xiaozhi từ Internet bằng Cloudflare Tunnel (Windows)

Máy tính này vẫn chạy Xiaozhi Server và lưu dữ liệu/config cục bộ. Cloudflare Tunnel tạo kết nối đi ra từ máy tính, vì vậy không cần mở cổng trên router. Quick Tunnel không cần tài khoản/domain nhưng URL sẽ thay đổi; muốn hostname ổn định, dùng Named Tunnel với domain và DNS tương thích.

## Dùng thử miễn phí với Quick Tunnel

Bạn có thể dùng cách này ngay cả khi chỉ có `gehihibot.duckdns.org`; Quick Tunnel không sử dụng hostname DuckDNS mà cấp hai URL `trycloudflare.com` tạm thời. Không cần tài khoản Cloudflare hoặc domain riêng. Trên Windows có thể cài `cloudflared` bằng:

```powershell
winget install --id Cloudflare.cloudflared --exact
```

Sau đó mở PowerShell mới, khởi động Xiaozhi Server và chờ cổng `8080` lẫn `8000` hoạt động. Nếu chạy từ mã nguồn, cần Go `1.24.2` trở lên; lần chạy đầu tạo `.config.yaml` rồi thoát để bạn điền cấu hình model. Chạy lại server sau khi hoàn tất cấu hình. Mở PowerShell thứ hai tại thư mục repo và chạy:

```powershell
.\cloudflare\start-quick-tunnels.ps1
```

Script mở hai Quick Tunnel: một tới trang/OTA cổng `8080`, một tới WebSocket cổng `8000`. Nó sẽ in ra URL dashboard, OTA và WebSocket. Trong cấu hình hệ thống của Xiaozhi, đổi `web.websocket` thành URL `wss://...trycloudflare.com` vừa được in; khởi động lại Xiaozhi Server. Nhập URL OTA vừa được in vào firmware/thiết bị. Giữ cửa sổ PowerShell mở để cả hai Tunnel hoạt động.

URL được tạo lại khi chạy script lần sau, vì vậy cần cập nhật lại WebSocket và OTA URL. Bất kỳ ai biết URL dashboard đều có thể mở trang đăng nhập; hãy dùng mật khẩu quản trị mạnh và không chia sẻ URL. Quick Tunnel chỉ dành cho thử nghiệm, không có cam kết uptime và có giới hạn dịch vụ. [Tài liệu Quick Tunnel của Cloudflare](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).

Để dừng, nhấn `Ctrl+C` trong cửa sổ script. Log được lưu trong `logs/quick-tunnel-*.log`.

## Tunnel hostname ổn định

Phần dưới đây dành cho trường hợp có domain và DNS phù hợp với Named Tunnel. Hostname DuckDNS hiện tại không được dùng trong cấu hình ví dụ bên dưới.

## 1. Khởi động server cục bộ

Làm theo [hướng dẫn chạy nhanh](quick-start.md) để cấu hình model và chạy server. Xác nhận các địa chỉ sau mở được trên chính máy tính:

- `http://127.0.0.1:8080` — trang quản trị.
- `http://127.0.0.1:8080/api/ota/` — kiểm tra OTA.
- WebSocket server đang lắng nghe cổng `8000`.

Trang quản trị đã có sẵn trong `web/` và được server phục vụ trên cổng `8080`. Đăng nhập bằng tài khoản quản trị; lần khởi động đầu tiên, mật khẩu tạm được ghi trong log. Hãy đổi mật khẩu ngay sau khi đăng nhập.

## 2. Cài và tạo Tunnel

1. Cài `cloudflared` trên Windows theo tài liệu cài đặt Cloudflare, đăng nhập tài khoản và chọn domain đã được Cloudflare quản lý.
2. Mở PowerShell tại thư mục gốc repo, chạy:

   ```powershell
   cloudflared tunnel login
   cloudflared tunnel create xiaozhi-home
   ```

   Lệnh tạo Tunnel in ra UUID và lưu credentials JSON dưới `%USERPROFILE%\.cloudflared\<UUID>.json`.
3. Chọn hai hostname cùng domain, ví dụ `panel.example.com` và `robot.example.com`, rồi tạo DNS route:

   ```powershell
   cloudflared tunnel route dns xiaozhi-home panel.example.com
   cloudflared tunnel route dns xiaozhi-home robot.example.com
   ```

4. Sao chép `cloudflare/tunnel.example.yml` thành `cloudflare/tunnel.yml`. Điền UUID, đường dẫn credentials JSON, hostname dashboard và hostname robot. `tunnel.yml` bị Git bỏ qua để tránh commit thông tin định danh Tunnel.

## 3. Cấu hình địa chỉ thiết bị

Trong `.config.yaml` của server (hoặc trang cấu hình hệ thống), đặt địa chỉ WebSocket công khai:

```yaml
web:
  websocket: wss://robot.example.com
```

Khởi động lại server để cấu hình có hiệu lực. Trên thiết bị, đặt OTA URL thành:

```text
https://panel.example.com/api/ota/
```

Hostname `panel` chuyển HTTPS tới HTTP server cục bộ cổng `8080`, còn `robot` chuyển WebSocket bảo mật tới server cổng `8000`. Cloudflare Tunnel hỗ trợ WebSocket. Không yêu cầu mở inbound port trên router/firewall.

## 4. Chạy Tunnel

Khi server đã hoạt động, chạy trong PowerShell tại repo:

```powershell
.\cloudflare\start-tunnel.ps1
```

Giữ cửa sổ tiến trình mở để duy trì Tunnel; `Ctrl+C` sẽ ngắt truy cập Internet. Máy tính phải bật, có mạng và tiến trình server phải hoạt động. Truy cập dashboard tại hostname `panel` và kiểm tra OTA endpoint trước khi cấu hình thiết bị.

## Lưu ý truy cập

- Bật Cloudflare Access nếu muốn thêm lớp bảo vệ cho hostname dashboard. Giữ hostname robot không yêu cầu tương tác đăng nhập Access vì firmware không thể thực hiện bước này; vẫn dùng đăng nhập ứng dụng ở dashboard và kiểm tra cơ chế xác thực thiết bị của bạn.
- Không dùng Quick Tunnel làm địa chỉ OTA cố định: hostname thử nghiệm có thể thay đổi và một Quick Tunnel chỉ trỏ tới một origin, trong khi hệ thống cần đưa cả cổng quản trị/OTA và cổng WebSocket ra ngoài.
- Giữ `.config.yaml`, `config.db`, credentials JSON và log riêng tư. Không gửi các file này lên repo hoặc cho người khác.
- WebSocket là kết nối dài hạn; nếu Tunnel hoặc máy tính mất kết nối, thiết bị cần kết nối lại sau khi dịch vụ hoạt động trở lại.

Tài liệu Cloudflare: [Create a locally-managed tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/get-started/create-local-tunnel/) · [Tunnel ingress rules](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/configure-tunnels/local-management/configuration-file/) · [WebSockets](https://developers.cloudflare.com/network/websockets/).
