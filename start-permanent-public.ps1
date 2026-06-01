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
$configPath = Join-Path $appDir "permanent-tunnel.yml"
$serverLog = Join-Path $workDir "memory-map-server.log"
$serverErr = Join-Path $workDir "memory-map-server.err.log"
$tunnelLog = Join-Path $workDir "cloudflared-permanent.log"
$tunnelErr = Join-Path $workDir "cloudflared-permanent.err.log"

if (-not $cloudflared) {
  Write-Host "cloudflared was not found."
  exit 1
}

if (-not (Test-Path -LiteralPath $configPath)) {
  Write-Host "Permanent tunnel config was not found."
  Write-Host "Run setup first, for example:"
  Write-Host ".\setup-permanent-public.ps1 -Hostname memory.example.com"
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
      ($_.CommandLine -like "*cloudflared*" -and ($_.CommandLine -like "*127.0.0.1:8765*" -or $_.CommandLine -like "*permanent-tunnel.yml*"))
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
  -ArgumentList @("tunnel", "--config", $configPath, "run", "--no-autoupdate") `
  -RedirectStandardOutput $tunnelLog `
  -RedirectStandardError $tunnelErr `
  -WindowStyle Hidden `
  -PassThru

$publicUrl = (Get-Content -Raw -LiteralPath (Join-Path $appDir "PUBLIC_URL.txt")).Trim()
$reachable = $false
for ($i = 0; $i -lt 12; $i++) {
  Start-Sleep -Seconds 3
  try {
    Invoke-WebRequest -Uri $publicUrl -UseBasicParsing -TimeoutSec 20 | Out-Null
    $reachable = $true
    break
  } catch {
    if ($tunnel.HasExited) {
      break
    }
  }
}

if (-not $reachable) {
  Write-Host "Permanent URL is not reachable yet:"
  Write-Host $publicUrl
  Write-Host "Check logs:"
  Write-Host $tunnelErr
  exit 1
}

Write-Host ""
Write-Host "Memory Map is running on the permanent public URL."
Write-Host "Local URL:  http://127.0.0.1:8765"
Write-Host "Public URL: $publicUrl"
Write-Host ""
Write-Host "Keep this computer running, or install the app on a server for true 24/7 availability."
Write-Host "Server PID: $($server.Id)"
Write-Host "Tunnel PID: $($tunnel.Id)"
