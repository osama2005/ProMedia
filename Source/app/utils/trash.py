"""Safe file deletion: send files to the Recycle Bin where possible.

On Windows this uses the shell's SHFileOperationW so a mistaken duplicate
cleanup is recoverable.  Elsewhere it falls back to a plain unlink.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def send_to_trash(path: str | Path) -> bool:
    """Move *path* to the Recycle Bin (Windows) or delete it (other OS).

    Returns True when the file no longer exists at its original location.
    """
    target = Path(path)
    if not target.exists():
        return True

    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class SHFILEOPSTRUCTW(ctypes.Structure):
                _fields_ = [
                    ("hwnd", wintypes.HWND),
                    ("wFunc", wintypes.UINT),
                    ("pFrom", wintypes.LPCWSTR),
                    ("pTo", wintypes.LPCWSTR),
                    ("fFlags", ctypes.c_uint16),
                    ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p),
                    ("lpszProgressTitle", wintypes.LPCWSTR),
                ]

            # FO_DELETE = 3, FOF_ALLOWUNDO = 0x40, FOF_NOCONFIRMATION = 0x10,
            # FOF_NOERRORUI = 0x0400, FOF_SILENT = 0x0004
            op = SHFILEOPSTRUCTW()
            op.hwnd = None
            op.wFunc = 3
            op.pFrom = str(target.resolve()) + "\x00"
            op.pTo = None
            op.fFlags = 0x0004 | 0x0010 | 0x0040 | 0x0400
            result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
            if result == 0 and not op.fAnyOperationsAborted and not target.exists():
                return True
        except Exception:
            pass  # fall through to unlink

    try:
        target.unlink()
        return True
    except OSError:
        return not target.exists()


def trash_available() -> bool:
    """Whether recoverable deletion is available on this platform."""
    return os.name == "nt"
