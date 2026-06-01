$ErrorActionPreference = "Stop"
$python = "C:\Users\76619\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$appDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $appDir
& $python .\server.py --host 0.0.0.0 --port 8765
