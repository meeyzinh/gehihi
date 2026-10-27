param(
    [string]$Config = (Join-Path $PSScriptRoot "tunnel.yml")
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    throw "Không tìm thấy cloudflared. Hãy cài Cloudflare Tunnel rồi mở PowerShell mới."
}
if (-not (Test-Path -LiteralPath $Config)) {
    throw "Chưa có $Config. Sao chép tunnel.example.yml thành tunnel.yml và điền UUID, credentials, hostname."
}
$content = Get-Content -LiteralPath $Config -Raw
if ($content -match "YOUR_TUNNEL_UUID|YOUR_WINDOWS_USER|example\.com") {
    throw "tunnel.yml vẫn còn giá trị mẫu. Hãy điền thông tin Cloudflare Tunnel và hostname của bạn."
}

Write-Host "Đang kết nối Cloudflare Tunnel theo cấu hình $Config ..."
& cloudflared tunnel --config $Config run
if ($LASTEXITCODE -ne 0) {
    throw "cloudflared kết thúc với mã lỗi $LASTEXITCODE. Hãy kiểm tra hostname, UUID và credentials."
}
