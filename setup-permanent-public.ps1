param(
  [Parameter(Mandatory = $true)]
  [string]$Hostname,
  [string]$TunnelName = "memory-map",
  [switch]$OverwriteDns
)

$ErrorActionPreference = "Stop"

$appDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$cloudflaredCandidates = @(
  "C:\Program Files (x86)\cloudflared\cloudflared.exe",
  "C:\Program Files\cloudflared\cloudflared.exe"
)
$cloudflared = $cloudflaredCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

if (-not $cloudflared) {
  Write-Host "cloudflared was not found. Install it with:"
  Write-Host "winget install --id Cloudflare.cloudflared -e --accept-source-agreements --accept-package-agreements"
  exit 1
}

$cloudflaredHome = Join-Path $env:USERPROFILE ".cloudflared"
$originCert = Join-Path $cloudflaredHome "cert.pem"

if (-not (Test-Path -LiteralPath $originCert)) {
  Write-Host "A browser login will open. Sign in to Cloudflare and choose the domain zone."
  & $cloudflared tunnel login
}

$tunnel = $null
try {
  $listJson = & $cloudflared tunnel list --output json 2>$null
  if ($listJson) {
    $tunnels = $listJson | ConvertFrom-Json
    $tunnel = $tunnels | Where-Object { $_.name -eq $TunnelName -and -not $_.deleted_at } | Select-Object -First 1
  }
} catch {
  $tunnel = $null
}

if (-not $tunnel) {
  Write-Host "Creating tunnel: $TunnelName"
  $createJson = & $cloudflared tunnel create $TunnelName --output json
  $tunnel = $createJson | ConvertFrom-Json
}

$tunnelId = if ($tunnel.id) { $tunnel.id } elseif ($tunnel.ID) { $tunnel.ID } else { $null }
if (-not $tunnelId) {
  throw "Could not determine tunnel id."
}

$credentialsFile = Join-Path $cloudflaredHome "$tunnelId.json"
if (-not (Test-Path -LiteralPath $credentialsFile)) {
  throw "Credentials file was not found: $credentialsFile"
}

$routeArgs = @("tunnel", "route", "dns")
if ($OverwriteDns) {
  $routeArgs += "--overwrite-dns"
}
$routeArgs += @($TunnelName, $Hostname)
& $cloudflared @routeArgs

$configPath = Join-Path $appDir "permanent-tunnel.yml"
$publicUrl = "https://$Hostname"
$yaml = @(
  "tunnel: $tunnelId",
  "credentials-file: '$credentialsFile'",
  "",
  "ingress:",
  "  - hostname: $Hostname",
  "    service: http://127.0.0.1:8765",
  "  - service: http_status:404"
)
Set-Content -LiteralPath $configPath -Value $yaml -Encoding ASCII
Set-Content -LiteralPath (Join-Path $appDir "PUBLIC_URL.txt") -Value $publicUrl -Encoding ASCII

Write-Host ""
Write-Host "Permanent public URL is configured:"
Write-Host $publicUrl
Write-Host ""
Write-Host "Start it with:"
Write-Host ".\start-permanent-public.ps1"
