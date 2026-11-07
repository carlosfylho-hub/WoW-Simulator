"""PyInstaller entry point for the standalone desktop app (Simulador WoW)."""

from __future__ import annotations

from wowsim.web.desktop import run

if __name__ == "__main__":
    run()
