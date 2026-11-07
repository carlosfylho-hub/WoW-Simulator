# Build the standalone SimuladorWoW.exe (pywebview + FastAPI + SimC).
# Usage: powershell -ExecutionPolicy Bypass -File scripts/build_desktop.ps1
param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Frontend = Join-Path (Split-Path -Parent $Root) "Simulator-WoW"

Write-Host "1/3 Build do frontend (Vite)..." -ForegroundColor Cyan
Push-Location $Frontend
try {
    if (-not (Test-Path "node_modules")) { npm install --no-audit --no-fund }
    npm run build
}
finally {
    Pop-Location
}

Write-Host "2/3 Dependencias de empacotamento..." -ForegroundColor Cyan
& $Python -m pip install --quiet "pyinstaller>=6.6" "pywebview>=5.0"

Write-Host "3/3 PyInstaller (one-file)..." -ForegroundColor Cyan
Push-Location $Root
try {
    $env:PYTHONPATH = "src"
    & $Python -m PyInstaller packaging/wowsim.spec --noconfirm --clean `
        --distpath dist_app --workpath build_app
}
finally {
    Pop-Location
}

$exe = Join-Path $Root "dist_app/SimuladorWoW.exe"
if (Test-Path $exe) {
    Write-Host "Pronto: $exe" -ForegroundColor Green
}
else {
    throw "Falha: $exe nao gerado"
}
