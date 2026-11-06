"""Project paths, with environment overrides for tests and alternative installs."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DADOS_DIR = Path(os.environ.get("WOWSIM_DADOS", PROJECT_ROOT / "dados")).resolve()
DERIVADOS_DIR = DADOS_DIR / "derivados"
SIMC_SRC_DIR = Path(
    os.environ.get("WOWSIM_SIMC_SRC", PROJECT_ROOT.parent / "simc-midnight")
).resolve()
