"""Standalone desktop window (pywebview) over the local FastAPI app.

The Python backend keeps running in a thread and pywebview opens a native
window (WebView2 on Windows) pointing at ``http://127.0.0.1:<port>``. No browser
or terminal is exposed to the user.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager

import uvicorn

from .app import app as fastapi_app


def porta_livre(host: str, porta: int) -> int:
    """Return ``porta`` if it is a free positive port, else a concrete free port."""
    if porta and porta > 0:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, porta))
                return porta
            except OSError:
                pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def _saudavel(url: str, timeout: float) -> bool:
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resposta:  # noqa: S310
                if resposta.status == 200:
                    return True
        except Exception:  # noqa: BLE001 - server not ready yet
            time.sleep(0.15)
    return False


def _verificar_frontend(base: str) -> None:
    """Smoke assertion: the bundled React index must be served."""
    try:
        with urllib.request.urlopen(f"{base}/", timeout=5.0) as resposta:  # noqa: S310
            html = resposta.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"O frontend não respondeu: {exc}") from exc
    if 'id="root"' not in html:
        raise RuntimeError("O frontend embutido não parece ser o app React.")


@contextmanager
def servidor_local(host: str = "127.0.0.1", porta: int = 0, timeout: float = 15.0) -> Iterator[str]:
    """Run the FastAPI app in a background thread; yield its base URL."""
    porta = porta_livre(host, porta)
    config = uvicorn.Config(
        fastapi_app,
        host=host,
        port=porta,
        log_level="warning",
    )
    servidor = uvicorn.Server(config)
    thread = threading.Thread(target=servidor.run, daemon=True)
    thread.start()
    base = f"http://{host}:{porta}"
    try:
        if not _saudavel(f"{base}/api/health", timeout):
            raise RuntimeError("O servidor local não respondeu a tempo.")
        yield base
    finally:
        servidor.should_exit = True
        thread.join(timeout=5)


def run(host: str = "127.0.0.1", port: int = 0, *, abrir_janela: bool = True) -> None:
    """Open the desktop window backed by the local server."""
    # Windowed PyInstaller builds have no console; avoid None stdout in uvicorn.
    if sys.stdout is None or sys.stderr is None:
        _nulo = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
        sys.stdout = sys.stdout or _nulo
        sys.stderr = sys.stderr or _nulo
    # Smoke test hook: start the server, verify health, then exit without a GUI.
    if os.environ.get("WOWSIM_SMOKE_EXIT"):
        abrir_janela = False
    with servidor_local(host, port) as base:
        if not abrir_janela:
            _verificar_frontend(base)
            return
        try:
            import webview
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError(
                "pywebview ausente. Instale com: pip install -e \".[desktop]\""
            ) from exc
        webview.create_window("Simulador WoW — Midnight S2", base, width=1366, height=860)
        webview.start()
