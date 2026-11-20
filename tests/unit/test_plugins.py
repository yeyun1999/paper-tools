"""Unit tests: plugin registration, validation, override, entry-point discovery."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from paper_search.core.errors import PluginError, UsageError
from paper_search.core.plugins import ROLE_GROUPS, PluginContext, PluginMeta, PluginRegistry
from tests.conftest import FakeDownloader, FakeExtractor, FakeLocator, FakeMetadata, FakeSearcher


def test_register_all_roles(plugin_ctx: PluginContext) -> None:
    registry = PluginRegistry(plugin_ctx)
    registry.register("searcher", FakeSearcher())
    registry.register("metadata", FakeMetadata())
    registry.register("locator", FakeLocator())
    registry.register("downloader", FakeDownloader())
    registry.register("extractor", FakeExtractor())
    assert registry.names("searcher") == ["fake"]
    assert registry.names("metadata") == ["fake"]
    assert registry.get("downloader", "fake_dl").meta.name == "fake_dl"
    described = registry.describe()
    assert set(described) == set(ROLE_GROUPS)
    assert described["downloader"][0]["formats"] == ["pdf", "xml"]


def test_register_invalid_plugin(plugin_ctx: PluginContext) -> None:
    registry = PluginRegistry(plugin_ctx)
    broken = SimpleNamespace(meta=PluginMeta(name="broken", version="0"))
    with pytest.raises(PluginError):
        registry.register("searcher", broken)


def test_unknown_role(plugin_ctx: PluginContext) -> None:
    registry = PluginRegistry(plugin_ctx)
    with pytest.raises(PluginError):
        registry.register("bogus", FakeSearcher())


def test_get_unknown_name(plugin_ctx: PluginContext) -> None:
    registry = PluginRegistry(plugin_ctx)
    with pytest.raises(UsageError, match="No searcher plugin"):
        registry.get("searcher", "nope")


def test_override_warns(plugin_ctx: PluginContext) -> None:
    registry = PluginRegistry(plugin_ctx)
    registry.register("searcher", FakeSearcher())
    registry.register("searcher", FakeSearcher())
    assert len(registry.load_warnings) == 1
    assert "overrides" in registry.load_warnings[0]


def test_discovery_via_entry_points(
    plugin_ctx: PluginContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_load() -> type:
        raise RuntimeError("boom")

    def fake_entry_points(*, group: str) -> list[SimpleNamespace]:
        if group == "paper_search.searchers":
            return [SimpleNamespace(name="fake", load=lambda: FakeSearcher)]
        if group == "paper_search.downloaders":
            return [
                SimpleNamespace(name="broken", load=broken_load),
                SimpleNamespace(name="fake_dl", load=lambda: FakeDownloader),
            ]
        return []

    monkeypatch.setattr("paper_search.core.plugins.entry_points", fake_entry_points)
    registry = PluginRegistry.discover(plugin_ctx)
    assert registry.names("searcher") == ["fake"]
    assert registry.names("downloader") == ["fake_dl"]
    assert any("broken" in w for w in registry.load_warnings)
