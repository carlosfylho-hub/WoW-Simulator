"""Project paths, with environment overrides for tests and alternative installs."""

from __future__ import annotations

import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    # When bundled by PyInstaller the resources live in the extraction dir.
    PROJECT_ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[2]

DADOS_DIR = Path(os.environ.get("WOWSIM_DADOS", PROJECT_ROOT / "dados")).resolve()
DERIVADOS_DIR = DADOS_DIR / "derivados"
SIMC_SRC_DIR = Path(
    os.environ.get("WOWSIM_SIMC_SRC", PROJECT_ROOT.parent / "simc-midnight")
).resolve()
