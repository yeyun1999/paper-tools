"""Caching: diskcache KV for HTTP responses/file mappings + sha256 file store."""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import tempfile
import threading
from contextlib import suppress
from pathlib import Path
from typing import Any

import diskcache
import platformdirs

logger = logging.getLogger(__name__)


class Cache:
    def __init__(self, root: Path | None = None, *, enabled: bool = True) -> None:
        self.enabled = enabled
        self.root = root or Path(platformdirs.user_cache_dir("paper-tools", appauthor=False))
        self._dc: diskcache.Cache | None = (
            diskcache.Cache(str(self.root / "kv")) if enabled else None
        )
        self._file_lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        if self._dc is None:
            return None
        return self._dc.get(key)

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        if self._dc is not None:
            self._dc.set(key, value, expire=ttl)

    def clear(self, *, include_artifacts: bool = False) -> int:
        if self._dc is not None:
            count = len(self._dc)
            self._dc.clear()
        else:
            count = 0
        if include_artifacts:
            artifacts = self.root / "papers"
            if artifacts.exists():
                shutil.rmtree(artifacts)
        return count

    def stats(self) -> dict[str, Any]:
        kv_size = self._dc.volume() if self._dc is not None else 0
        artifact_files, artifact_size = self._artifact_stats()
        return {
            "enabled": self.enabled,
            "path": str(self.root),
            "entries": len(self._dc) if self._dc is not None else 0,
            "size_bytes": kv_size + artifact_size,
            "kv_size_bytes": kv_size,
            "artifact_files": artifact_files,
            "artifact_size_bytes": artifact_size,
        }

    def _artifact_files(self) -> list[Path]:
        artifacts = self.root / "papers"
        if not artifacts.exists():
            return []
        return [path for path in artifacts.iterdir() if path.is_file()]

    def _artifact_stats(self) -> tuple[int, int]:
        count = 0
        size = 0
        for path in self._artifact_files():
            count += 1
            with suppress(OSError):
                size += path.stat().st_size
        return count, size

    # ---- file store (PDF/XML/text artifacts) ----

    def file_path(self, sha256: str, ext: str) -> Path:
        return self.root / "papers" / f"{sha256}.{ext}"

    @staticmethod
    def _matches(path: Path, digest: str) -> bool:
        try:
            with path.open("rb") as stream:
                return hashlib.file_digest(stream, "sha256").hexdigest() == digest
        except OSError:
            return False

    def store_file(self, data: bytes, ext: str) -> tuple[Path, str]:
        digest = hashlib.sha256(data).hexdigest()
        path = self.file_path(digest, ext)
        if not self.enabled:
            return path, digest
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._file_lock:
            if path.exists() and self._matches(path, digest):
                return path, digest

            temp_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    dir=path.parent, prefix=f".{path.name}.", delete=False
                ) as stream:
                    temp_path = Path(stream.name)
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                try:
                    temp_path.replace(path)
                except PermissionError:
                    if not path.exists() or not self._matches(path, digest):
                        raise
            finally:
                if temp_path is not None:
                    temp_path.unlink(missing_ok=True)
        return path, digest

    def get_file(self, sha256: str, ext: str) -> Path | None:
        if not self.enabled:
            return None
        path = self.file_path(sha256, ext)
        if not path.is_file():
            return None
        if not self._matches(path, sha256):
            logger.warning("Removing corrupt cached artifact %s", path)
            try:
                path.unlink()
            except OSError:
                logger.warning("Could not remove corrupt cached artifact %s", path, exc_info=True)
            return None
        return path

    def prune_orphans(self) -> int:
        if self._dc is None:
            return 0
        referenced: set[str] = set()
        for key in self._dc.iterkeys():
            if not isinstance(key, str) or not key.startswith("file:"):
                continue
            mapping = self._dc.get(key)
            if not isinstance(mapping, dict):
                continue
            digest = mapping.get("sha256")
            ext = mapping.get("ext")
            if isinstance(digest, str) and isinstance(ext, str):
                referenced.add(self.file_path(digest, ext).name)

        removed = 0
        for path in self._artifact_files():
            if path.name in referenced:
                continue
            try:
                path.unlink()
                removed += 1
            except OSError:
                logger.warning("Could not remove orphaned artifact %s", path, exc_info=True)
        return removed
