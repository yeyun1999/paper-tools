"""Caching: diskcache KV for responses/metadata + sha256-addressed file store."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import diskcache
import platformdirs


class Cache:
    def __init__(self, root: Path | None = None, *, enabled: bool = True) -> None:
        self.enabled = enabled
        self.root = root or Path(platformdirs.user_cache_dir("paper-tools", appauthor=False))
        self._dc: diskcache.Cache | None = (
            diskcache.Cache(str(self.root / "kv")) if enabled else None
        )

    def get(self, key: str) -> Any | None:
        if self._dc is None:
            return None
        return self._dc.get(key)

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        if self._dc is not None:
            self._dc.set(key, value, expire=ttl)

    def clear(self) -> int:
        if self._dc is None:
            return 0
        count = len(self._dc)
        self._dc.clear()
        return count

    def stats(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "path": str(self.root),
            "entries": len(self._dc) if self._dc is not None else 0,
            "size_bytes": self._dc.volume() if self._dc is not None else 0,
        }

    # ---- file store (PDF/XML/text artifacts) ----

    def file_path(self, sha256: str, ext: str) -> Path:
        return self.root / "papers" / f"{sha256}.{ext}"

    def store_file(self, data: bytes, ext: str) -> tuple[Path, str]:
        digest = hashlib.sha256(data).hexdigest()
        path = self.file_path(digest, ext)
        if self.enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_bytes(data)
        return path, digest

    def get_file(self, sha256: str, ext: str) -> Path | None:
        if not self.enabled:
            return None
        path = self.file_path(sha256, ext)
        return path if path.exists() else None
