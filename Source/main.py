"""Pro Media Downloader - application entry point."""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def _enable_windows_dpi_awareness() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # type: ignore[attr-defined]
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()  # type: ignore[attr-defined]
        except Exception:
            pass


def main() -> None:
    _enable_windows_dpi_awareness()
    from app.ui.app import run_app
    from app.utils.logger import log

    try:
        run_app()
    except Exception:
        log.exception("Fatal startup error")
        raise


if __name__ == "__main__":
    main()
