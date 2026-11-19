"""Streaming SHA-256 helpers for download integrity checks."""

from __future__ import annotations

import hashlib
from pathlib import Path

HASH_CHUNK = 1024 * 1024  # 1 MiB - small enough to stay responsive on big files


def sha256_file(path: str | Path, chunk_size: int = HASH_CHUNK) -> str:
    """Return the lowercase SHA-256 hex digest of *path* without loading it whole."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_sha256(value: str) -> str:
    """Normalise a user-supplied digest; return ``""`` when it is not SHA-256."""
    text = "".join(str(value or "").split()).lower()
    if text.startswith("sha256:"):
        text = text[7:]
    if text.startswith("0x"):
        text = text[2:]
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        return ""
    return text
