param(
    [int]$HttpPort = 0,
    [int]$WsPort = 8000
)

$ErrorActionPreference = "Stop"

$cloudflared = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $cloudflared) {
    $fallbackPaths = @(
        "C:\Program Files (x86)\cloudflared\cloudflared.exe",
        "C:\Program Files\cloudflared\cloudflared.exe",
        "$env:LOCALAPPDATA\Microsoft\WinGet\Links\cloudflared.exe"
    )
    foreach ($path in $fallbackPaths) {
        if (Test-Path -LiteralPath $path) {
            $cloudflared = [PSCustomObject]@{ Source = $path }
            break
        }
    }
}

if (-not $cloudflared) {
    throw "Không tìm thấy cloudflared. Hãy cài cloudflared bằng 'winget install --id Cloudflare.cloudflared --exact' và mở PowerShell mới."
}

# Tự động nhận diện cổng HTTP nếu chưa chỉ định (8003 cho Gehihi Python server, 8080 cho Xiaozhi Go server)
if ($HttpPort -eq 0) {
    if (Test-NetConnection -ComputerName 127.0.0.1 -Port 8003 -InformationLevel Quiet) {
        $HttpPort = 8003
    } elseif (Test-NetConnection -ComputerName 127.0.0.1 -Port 8080 -InformationLevel Quiet) {
        $HttpPort = 8080
    } else {
        throw "Không tìm thấy server HTTP nào đang chạy trên cổng 8003 hoặc 8080. Hãy khởi động server trước."
    }
}

if (-not (Test-NetConnection -ComputerName 127.0.0.1 -Port $HttpPort -InformationLevel Quiet)) {
    throw "Không kết nối được cổng HTTP $HttpPort. Hãy khởi động server trước."
}

if (-not (Test-NetConnection -ComputerName 127.0.0.1 -Port $WsPort -InformationLevel Quiet)) {
    throw "Không kết nối được cổng WebSocket $WsPort. Hãy khởi động server trước."
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $repoRoot "logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$panelOut = Join-Path $logDir "quick-tunnel-panel.out.log"
$panelErr = Join-Path $logDir "quick-tunnel-panel.err.log"
$wsOut = Join-Path $logDir "quick-tunnel-robot.out.log"
$wsErr = Join-Path $logDir "quick-tunnel-robot.err.log"
Remove-Item -LiteralPath $panelOut, $panelErr, $wsOut, $wsErr -Force -ErrorAction SilentlyContinue

$processes = @()
try {
    Write-Host "Đang khởi tạo 2 Quick Tunnel..." -ForegroundColor Yellow
    Write-Host "  1) HTTP/Dashboard (127.0.0.1:$HttpPort)"
    Write-Host "  2) WebSocket Robot (127.0.0.1:$WsPort)"

    $processes += Start-Process -FilePath $cloudflared.Source -ArgumentList @("tunnel", "--url", "http://127.0.0.1:$HttpPort") -PassThru -WindowStyle Hidden -RedirectStandardOutput $panelOut -RedirectStandardError $panelErr
    $processes += Start-Process -FilePath $cloudflared.Source -ArgumentList @("tunnel", "--url", "http://127.0.0.1:$WsPort") -PassThru -WindowStyle Hidden -RedirectStandardOutput $wsOut -RedirectStandardError $wsErr

    $panelUrl = $null
    $robotUrl = $null
    for ($attempt = 0; $attempt -lt 60 -and (-not $panelUrl -or -not $robotUrl); $attempt++) {
        foreach ($process in $processes) {
            $process.Refresh()
            if ($process.HasExited) {
                throw "cloudflared đã dừng. Xem log trong thư mục logs để biết nguyên nhân."
            }
        }

        $panelLogs = @()
        foreach ($path in @($panelOut, $panelErr)) {
            if (Test-Path -LiteralPath $path) { $panelLogs += Get-Content -LiteralPath $path -Raw }
        }
        $robotLogs = @()
        foreach ($path in @($wsOut, $wsErr)) {
            if (Test-Path -LiteralPath $path) { $robotLogs += Get-Content -LiteralPath $path -Raw }
        }
        $panelUrl = [regex]::Match(($panelLogs -join "`n"), "https://[a-z0-9-]+\.trycloudflare\.com").Value
        $robotUrl = [regex]::Match(($robotLogs -join "`n"), "https://[a-z0-9-]+\.trycloudflare\.com").Value
        if (-not $panelUrl -or -not $robotUrl) { Start-Sleep -Seconds 1 }
    }

    if (-not $panelUrl -or -not $robotUrl) {
        throw "Chưa lấy được URL Quick Tunnel sau 60 giây. Xem log trong thư mục logs."
    }

    $otaEndpoint = if ($HttpPort -eq 8003) { "$panelUrl/xiaozhi/ota/" } else { "$panelUrl/api/ota/" }
    $wsRobotUrl = $robotUrl -replace '^https://', 'wss://'

    # Nếu đang chạy Gehihi server trên cổng 8003, tự động đăng ký Tunnel URL với backend
    if ($HttpPort -eq 8003) {
        try {
            $regBody = @{ tunnel_url = $panelUrl } | ConvertTo-Json
            Invoke-RestMethod -Uri "http://127.0.0.1:8003/xiaozhi/tunnel/register" -Method Post -Body $regBody -ContentType "application/json" -TimeoutSec 3 | Out-Null
            Write-Host ">> Đã tự động cập nhật URL Tunnel vào Gehihi Server!" -ForegroundColor Green
        } catch {
            # Bỏ qua nếu endpoint chưa sẵn sàng
        }
    }

    Write-Host ""
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host "   QUICK TUNNEL ĐANG CHẠY THÀNH CÔNG (URL TỰ ĐỘNG CẤP)    " -ForegroundColor Cyan
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host "Dashboard Quản trị : $panelUrl" -ForegroundColor White
    Write-Host "OTA URL cho Robot  : $otaEndpoint" -ForegroundColor White
    Write-Host "WebSocket Robot    : $wsRobotUrl" -ForegroundColor White
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host "Lưu ý:"
    Write-Host "- Cập nhật WebSocket URL ($wsRobotUrl) vào cấu hình Robot nếu dùng WebSocket riêng."
    Write-Host "- Giữ cửa sổ này mở để duy trì Tunnel. Nhấn Ctrl+C để dừng."
    Write-Host ""

    while ($true) {
        foreach ($process in $processes) {
            $process.Refresh()
            if ($process.HasExited) {
                throw "Một Quick Tunnel đã dừng. Xem log trong thư mục logs."
            }
        }
        Start-Sleep -Seconds 2
    }
}
finally {
    foreach ($process in $processes) {
        if ($process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
}

