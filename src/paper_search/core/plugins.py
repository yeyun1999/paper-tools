"""Five-role plugin machinery: entry-point discovery, registry, protocols.

Roles map to the pipeline ``search -> enrich -> locate -> download -> extract``.
A plugin class may implement several roles and register in several groups.
"""

from __future__ import annotations

import builtins
import logging
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import Any, Protocol

from paper_search.core.cache import Cache
from paper_search.core.config import AppConfig
from paper_search.core.errors import PluginError, UsageError
from paper_search.core.http import HttpClient
from paper_search.core.models import Artifact, FullTextCandidate, Paper, SearchPage
from paper_search.core.query import Query

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PluginMeta:
    name: str
    version: str
    description: str = ""


@dataclass
class PluginContext:
    config: AppConfig
    http: HttpClient
    cache: Cache


class Searcher(Protocol):
    meta: PluginMeta

    def search(self, q: Query, *, limit: int = 20, cursor: str | None = None) -> SearchPage: ...


class MetadataProvider(Protocol):
    meta: PluginMeta
    id_kinds: frozenset[str]

    def enrich(self, paper: Paper) -> Paper: ...


class Locator(Protocol):
    meta: PluginMeta

    def resolve(self, paper: Paper) -> list[FullTextCandidate]: ...


class Downloader(Protocol):
    meta: PluginMeta
    formats: frozenset[str]

    def supports(self, candidate: FullTextCandidate) -> bool: ...

    def download(self, candidate: FullTextCandidate) -> Artifact: ...


class Extractor(Protocol):
    meta: PluginMeta
    source_formats: frozenset[str]

    def extract(self, data: bytes, *, source_format: str) -> str: ...


ROLE_GROUPS: dict[str, str] = {
    "searcher": "paper_search.searchers",
    "metadata": "paper_search.metadata",
    "locator": "paper_search.locators",
    "downloader": "paper_search.downloaders",
    "extractor": "paper_search.extractors",
}


def available_names(role: str) -> list[str]:
    """Installed entry-point names for a role (help text only; no instantiation)."""
    return sorted({ep.name for ep in entry_points(group=ROLE_GROUPS[role])})


_REQUIRED_ATTRS: dict[str, tuple[str, ...]] = {
    "searcher": ("meta", "search"),
    "metadata": ("meta", "id_kinds", "enrich"),
    "locator": ("meta", "resolve"),
    "downloader": ("meta", "formats", "supports", "download"),
    "extractor": ("meta", "source_formats", "extract"),
}


class PluginRegistry:
    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        self._plugins: dict[str, dict[str, Any]] = {role: {} for role in ROLE_GROUPS}
        self.load_warnings: list[str] = []

    def register(self, role: str, plugin: Any) -> None:
        if role not in self._plugins:
            raise PluginError(f"Unknown plugin role {role!r}")
        for attr in _REQUIRED_ATTRS[role]:
            if not hasattr(plugin, attr):
                raise PluginError(
                    f"{role} plugin {getattr(plugin, 'meta', plugin)!r} missing {attr!r}"
                )
        meta = plugin.meta
        if not isinstance(meta, PluginMeta):
            raise PluginError(f"{role} plugin has invalid meta (expected PluginMeta)")
        if meta.name in self._plugins[role]:
            message = f"plugin {meta.name!r} ({role}) overrides an earlier registration"
            logger.warning(message)
            self.load_warnings.append(message)
        self._plugins[role][meta.name] = plugin

    def get(self, role: str, name: str) -> Any:
        plugins = self._plugins.get(role, {})
        if name not in plugins:
            available = ", ".join(sorted(plugins)) or "(none)"
            raise UsageError(f"No {role} plugin named {name!r}; available: {available}")
        return plugins[name]

    def list(self, role: str) -> builtins.list[Any]:
        return list(self._plugins.get(role, {}).values())

    def names(self, role: str) -> builtins.list[str]:
        return sorted(self._plugins.get(role, {}))

    def describe(self) -> dict[str, builtins.list[dict[str, Any]]]:
        """Plugin inventory for the sources command."""
        result: dict[str, builtins.list[dict[str, Any]]] = {}
        for role, plugins in self._plugins.items():
            entries = []
            for plugin in plugins.values():
                info: dict[str, Any] = {
                    "name": plugin.meta.name,
                    "version": plugin.meta.version,
                    "description": plugin.meta.description,
                }
                for attr in ("id_kinds", "formats", "source_formats"):
                    if hasattr(plugin, attr):
                        info[attr] = sorted(getattr(plugin, attr))
                entries.append(info)
            result[role] = entries
        return result

    @classmethod
    def discover(cls, ctx: PluginContext) -> PluginRegistry:
        registry = cls(ctx)
        for role, group in ROLE_GROUPS.items():
            for ep in entry_points(group=group):
                try:
                    plugin_cls = ep.load()
                    plugin = plugin_cls(ctx)
                    registry.register(role, plugin)
                except Exception as exc:
                    message = f"failed to load {role} plugin {ep.name!r}: {exc}"
                    logger.warning(message)
                    registry.load_warnings.append(message)
        return registry
