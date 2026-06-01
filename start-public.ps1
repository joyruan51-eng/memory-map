$ErrorActionPreference = "Stop"

$appDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent (Split-Path -Parent $appDir)
$workDir = Join-Path $rootDir "work"
$python = "C:\Users\76619\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$cloudflaredCandidates = @(
  "C:\Program Files (x86)\cloudflared\cloudflared.exe",
  "C:\Program Files\cloudflared\cloudflared.exe"
)
$cloudflared = $cloudflaredCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
$serverLog = Join-Path $workDir "memory-map-server.log"
$serverErr = Join-Path $workDir "memory-map-server.err.log"
$tunnelLog = Join-Path $workDir "cloudflared.log"
$tunnelErr = Join-Path $workDir "cloudflared.err.log"

if (-not $cloudflared) {
  Write-Host "cloudflared was not found. Install it with:"
  Write-Host "winget install --id Cloudflare.cloudflared -e --accept-source-agreements --accept-package-agreements"
  exit 1
}

New-Item -ItemType Directory -Force -Path $workDir | Out-Null

Get-CimInstance Win32_Process |
  Where-Object {
    $_.ProcessId -ne $PID -and
    (
      $_.CommandLine -like "*memory-map*server.py*" -or
      $_.CommandLine -like "*server.py --host*8765*" -or
      $_.CommandLine -like "*localhost.run*" -or
      ($_.CommandLine -like "*cloudflared*" -and $_.CommandLine -like "*127.0.0.1:8765*")
    )
  } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Remove-Item -LiteralPath $serverLog, $serverErr, $tunnelLog, $tunnelErr -Force -ErrorAction SilentlyContinue

$server = Start-Process -FilePath $python `
  -ArgumentList @("server.py", "--host", "127.0.0.1", "--port", "8765") `
  -WorkingDirectory $appDir `
  -WindowStyle Hidden `
  -RedirectStandardOutput $serverLog `
  -RedirectStandardError $serverErr `
  -PassThru

Start-Sleep -Seconds 1
Invoke-WebRequest -Uri "http://127.0.0.1:8765/" -UseBasicParsing -TimeoutSec 10 | Out-Null

$tunnel = Start-Process -FilePath $cloudflared `
  -ArgumentList @("tunnel", "--url", "http://127.0.0.1:8765", "--no-autoupdate") `
  -RedirectStandardOutput $tunnelLog `
  -RedirectStandardError $tunnelErr `
  -WindowStyle Hidden `
  -PassThru

$publicUrl = $null
for ($i = 0; $i -lt 90; $i++) {
  Start-Sleep -Seconds 1
  $text = ""
  if (Test-Path -LiteralPath $tunnelLog) {
    $text += Get-Content -Raw -LiteralPath $tunnelLog
  }
  if (Test-Path -LiteralPath $tunnelErr) {
    $text += "`n"
    $text += Get-Content -Raw -LiteralPath $tunnelErr
  }
  if ($text) {
    $match = [regex]::Match($text, "https://[a-zA-Z0-9-]+\.trycloudflare\.com")
    if ($match.Success) {
      $publicUrl = $match.Value
      break
    }
  }
  if ($tunnel.HasExited) {
    break
  }
}

if (-not $publicUrl) {
  Write-Host "Public URL was not generated yet. Check logs:"
  Write-Host $tunnelLog
  Write-Host $tunnelErr
  exit 1
}

$reachable = $false
for ($i = 0; $i -lt 8; $i++) {
  try {
    Invoke-WebRequest -Uri $publicUrl -UseBasicParsing -TimeoutSec 20 | Out-Null
    $reachable = $true
    break
  } catch {
    Start-Sleep -Seconds 3
  }
}

if (-not $reachable) {
  Write-Host "Public URL was generated but is not reachable yet:"
  Write-Host $publicUrl
  Write-Host "Try again in a few seconds, or check logs:"
  Write-Host $tunnelErr
  exit 1
}

Set-Content -LiteralPath (Join-Path $appDir "PUBLIC_URL.txt") -Value $publicUrl -Encoding ASCII

Write-Host ""
Write-Host "Memory Map is running."
Write-Host "Local URL:  http://127.0.0.1:8765"
Write-Host "Public URL: $publicUrl"
Write-Host ""
Write-Host "Keep this computer and these background processes running."
Write-Host "Server PID: $($server.Id)"
Write-Host "Tunnel PID: $($tunnel.Id)"
