# Build SimulationCraft from the midnight branch on Windows.
# Requires: git, cmake, ninja and a C++ compiler (Visual Studio Build Tools).
# In a 2-core machine the build takes about 35 minutes.

param(
    [int]$Jobs = 0,
    [string]$Branch = "midnight"
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$sourceDir = Join-Path $projectRoot ".simc-src"
$buildDir = Join-Path $sourceDir "build"
$binDir = Join-Path $projectRoot "bin"

foreach ($tool in @("git", "cmake", "ninja")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "Ferramenta ausente: $tool. Instale antes de compilar."
    }
}

if ($Jobs -le 0) {
    $Jobs = [Math]::Max(1, [Environment]::ProcessorCount - 1)
}

if (-not (Test-Path (Join-Path $sourceDir ".git"))) {
    Write-Host "Clonando SimulationCraft ($Branch) em $sourceDir ..."
    git clone --depth 1 --branch $Branch https://github.com/simulationcraft/simc $sourceDir
    if ($LASTEXITCODE -ne 0) { throw "git clone falhou." }
} else {
    Write-Host "Repositório já existe em $sourceDir; reutilizando."
}

Write-Host "Configurando CMake (Release, sem GUI, sem rede) ..."
cmake -S $sourceDir -B $buildDir -G Ninja `
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
$executavel = $candidatos | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $executavel) {
    throw "Binário não encontrado depois do build. Procure manualmente em $buildDir."
}

New-Item -ItemType Directory -Force -Path $binDir | Out-Null
$destino = Join-Path $binDir "simc.exe"
Copy-Item -LiteralPath $executavel -Destination $destino -Force

Write-Host ""
Write-Host "Pronto: $destino"
& $destino --version
