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

Write-Host "Memory Map public service stopped."
