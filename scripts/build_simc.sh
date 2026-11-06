#!/usr/bin/env bash
# Build SimulationCraft from the midnight branch on Linux or macOS.
# Requires: git, cmake, ninja and a C++ compiler.
# In a 2-core machine the build takes about 35 minutes.

set -euo pipefail

BRANCH="${1:-midnight}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="$PROJECT_ROOT/.simc-src"
BUILD_DIR="$SOURCE_DIR/build"
BIN_DIR="$PROJECT_ROOT/bin"

for tool in git cmake ninja; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "Ferramenta ausente: $tool. Instale antes de compilar." >&2
        exit 1
    fi
done

if command -v nproc >/dev/null 2>&1; then
    NUCLEOS="$(nproc)"
elif command -v sysctl >/dev/null 2>&1; then
    NUCLEOS="$(sysctl -n hw.ncpu)"
else
    NUCLEOS=2
fi
JOBS=$(( NUCLEOS > 1 ? NUCLEOS - 1 : 1 ))

if [ ! -d "$SOURCE_DIR/.git" ]; then
    echo "Clonando SimulationCraft ($BRANCH) em $SOURCE_DIR ..."
    git clone --depth 1 --branch "$BRANCH" \
        https://github.com/simulationcraft/simc "$SOURCE_DIR"
else
    echo "Repositório já existe em $SOURCE_DIR; reutilizando."
fi

echo "Configurando CMake (Release, sem GUI, sem rede) ..."
cmake -S "$SOURCE_DIR" -B "$BUILD_DIR" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_GUI=OFF \
    -DSC_NO_NETWORKING=ON

echo "Compilando alvo simc com $JOBS job(s) ..."
cmake --build "$BUILD_DIR" --target simc -j "$JOBS"

EXECUTAVEL=""
for candidato in "$BUILD_DIR/simc" "$BUILD_DIR/simc.exe"; do
    if [ -f "$candidato" ]; then
        EXECUTAVEL="$candidato"
        break
    fi
done

if [ -z "$EXECUTAVEL" ]; then
    echo "Binário não encontrado depois do build. Procure manualmente em $BUILD_DIR." >&2
    exit 1
fi

mkdir -p "$BIN_DIR"
cp "$EXECUTAVEL" "$BIN_DIR/simc"
chmod +x "$BIN_DIR/simc"

echo
echo "Pronto: $BIN_DIR/simc"
"$BIN_DIR/simc" --version || true
