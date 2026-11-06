# Build SimulationCraft from source on Windows with CMake + Ninja + MSVC.
#
# Requires: git, cmake, ninja and Visual Studio Build Tools with the C++ workload.
# Install the tools with:
#   winget install Kitware.CMake Ninja-build.Ninja Microsoft.VisualStudio.2022.BuildTools
#
# Examples:
#   powershell -ExecutionPolicy Bypass -File scripts/build_simc.ps1
#   powershell -ExecutionPolicy Bypass -File scripts/build_simc.ps1 -SourceDir ..\..\simc-midnight

param(
    [string]$SourceDir = "",
    [string]$Branch = "midnight",
    [int]$Jobs = 0,
    [string]$InstallDir = "C:\VS2022BuildTools",
    [string]$VcVars = ""
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
if ($Jobs -le 0) {
    $Jobs = [Math]::Max(1, [Environment]::ProcessorCount - 1)
}

foreach ($tool in @("git", "cmake", "ninja")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "Ferramenta ausente: $tool. Instale antes de compilar."
    }
}

if (-not $VcVars) {
    $VcVars = Join-Path $InstallDir "VC\Auxiliary\Build\vcvars64.bat"
}
if (-not (Test-Path -LiteralPath $VcVars)) {
    throw "vcvars64.bat não encontrado em $VcVars. Instale o VS Build Tools com a carga C++ ou passe -VcVars."
}

# Import the MSVC environment into this process so Ninja picks up cl.exe.
Write-Host "Importando ambiente do MSVC de $VcVars ..."
$envLines = & cmd /c "call `"$VcVars`" >nul && set"
foreach ($line in $envLines) {
    if ($line -match '^([^=]+)=(.*)$') {
        Set-Item -Path "Env:$($matches[1])" -Value $matches[2]
    }
}

if (-not $SourceDir) {
    $SourceDir = Join-Path $projectRoot ".simc-src"
}
$SourceDir = [System.IO.Path]::GetFullPath($SourceDir)
$buildDir = Join-Path $SourceDir "build"
$binDir = Join-Path $projectRoot "bin"

if (-not (Test-Path (Join-Path $SourceDir ".git")) -and -not (Test-Path (Join-Path $SourceDir "CMakeLists.txt"))) {
    Write-Host "Clonando SimulationCraft ($Branch) em $SourceDir ..."
    git clone --depth 1 --branch $Branch https://github.com/simulationcraft/simc $SourceDir
    if ($LASTEXITCODE -ne 0) { throw "git clone falhou." }
}
else {
    Write-Host "Fonte já existe em $SourceDir; reutilizando."
}

Write-Host "Configurando CMake (Release, sem GUI, sem rede) ..."
cmake -S $SourceDir -B $buildDir -G Ninja `
    -DCMAKE_BUILD_TYPE=Release `
    -DBUILD_GUI=OFF `
    -DSC_NO_NETWORKING=ON
if ($LASTEXITCODE -ne 0) { throw "cmake configure falhou." }

Write-Host "Compilando alvo simc com $Jobs job(s) ..."
cmake --build $buildDir --target simc -j $Jobs
if ($LASTEXITCODE -ne 0) { throw "cmake build falhou." }

$candidatos = @(
    (Join-Path $buildDir "simc.exe"),
    (Join-Path $buildDir "simc"),
    (Join-Path $buildDir "Release\simc.exe")
)
$executavel = $candidatos | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $executavel) {
    throw "Binário não encontrado depois do build. Procure manualmente em $buildDir."
}

New-Item -ItemType Directory -Force -Path $binDir | Out-Null
$destino = Join-Path $binDir "simc.exe"
Copy-Item -LiteralPath $executavel -Destination $destino -Force

Write-Host ""
Write-Host "Pronto: $destino"
& $destino --version
