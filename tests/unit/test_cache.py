"""Unit tests for persistent and content-addressed cache behavior."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from paper_tools.core.cache import Cache


def test_store_and_get_file(tmp_path: Path) -> None:
    cache = Cache(root=tmp_path / "cache")
    path, digest = cache.store_file(b"cached content", "txt")
    assert path.name == f"{digest}.txt"
    assert cache.get_file(digest, "txt") == path
    assert path.read_bytes() == b"cached content"


def test_corrupt_file_is_rejected_and_removed(tmp_path: Path) -> None:
    cache = Cache(root=tmp_path / "cache")
    path, digest = cache.store_file(b"cached content", "txt")
    path.write_bytes(b"corrupt")
    assert cache.get_file(digest, "txt") is None
    assert not path.exists()


def test_concurrent_store_file_is_atomic(tmp_path: Path) -> None:
    cache = Cache(root=tmp_path / "cache")
    content = b"%PDF-1.4\n" + b"x" * 2048
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: cache.store_file(content, "pdf"), range(32)))
    digest = results[0][1]
    assert {item[1] for item in results} == {digest}
    assert cache.get_file(digest, "pdf") is not None
    assert not list((tmp_path / "cache" / "papers").glob(".*"))


def test_clear_all_removes_kv_and_artifacts(tmp_path: Path) -> None:
    cache = Cache(root=tmp_path / "cache")
    cache.set("key", "value")
    path, _ = cache.store_file(b"artifact", "txt")
    assert cache.clear(include_artifacts=True) == 1
    assert cache.get("key") is None
    assert not path.exists()


def test_stats_include_artifacts(tmp_path: Path) -> None:
    cache = Cache(root=tmp_path / "cache")
    cache.set("key", "value")
    _, digest = cache.store_file(b"artifact", "txt")
    stats = cache.stats()
    assert stats["entries"] == 1
    assert stats["artifact_files"] == 1
    assert stats["artifact_size_bytes"] == len(b"artifact")
    assert stats["size_bytes"] == stats["kv_size_bytes"] + len(b"artifact")
    assert cache.get_file(digest, "txt") is not None


def test_prune_orphans_keeps_referenced_files(tmp_path: Path) -> None:
    cache = Cache(root=tmp_path / "cache")
    _, referenced = cache.store_file(b"referenced", "txt")
    orphan, _ = cache.store_file(b"orphan", "txt")
    cache.set("file:test", {"sha256": referenced, "ext": "txt"})
    assert cache.prune_orphans() == 1
    assert not orphan.exists()
    assert cache.get_file(referenced, "txt") is not None
