# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: one-file SimuladorWoW desktop app.

Bundles the React build (Simulator-WoW/dist) as ``frontend/``, the data
snapshot as ``dados/``, the simc binary as ``bin/simc.exe`` and all Python
package data (Jinja templates). Set PYTHONPATH=src before building.
"""

import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))  # wow-sim/
SRC = os.path.join(ROOT, "src")

datas = []
frontend = os.path.abspath(os.path.join(ROOT, "..", "Simulator-WoW", "dist"))
if os.path.isdir(frontend):
    datas.append((frontend, "frontend"))
dados = os.path.join(ROOT, "dados")
if os.path.isdir(dados):
    datas.append((dados, "dados"))
datas += collect_data_files("wowsim")
datas += collect_data_files("webview")

binaries = []
simc = os.path.join(ROOT, "bin", "simc.exe")
if os.path.isfile(simc):
    binaries.append((simc, "bin"))

hiddenimports = []
for pacote in ("uvicorn", "fastapi", "starlette", "pydantic", "wowsim", "webview"):
    try:
        hiddenimports += collect_submodules(pacote)
    except Exception:
        pass
hiddenimports += [
    "webview.platforms.edgechromium",
    "clr_loader",
    "pythonnet",
]

a = Analysis(
    [os.path.join(SPECPATH, "wowsim_app.py")],
    pathex=[SRC],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter",
        # Heavy ML/scientific stacks that got pulled transitively; none are used.
        "torch",
        "torchvision",
        "numpy",
        "scipy",
        "pandas",
        "pyarrow",
        "matplotlib",
        "cv2",
        "numba",
        "llvmlite",
        "sentencepiece",
        "sklearn",
        "transformers",
        "tensorflow",
        "jax",
        "IPython",
        "notebook",
        "jupyter",
        "pytest",
        "IPython",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="SimuladorWoW",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    onefile=True,
)
