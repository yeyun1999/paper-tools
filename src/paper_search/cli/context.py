"""Global CLI options and service construction.

Commands access services via ``context.build_services(opts)`` (module attribute
lookup) so tests can monkeypatch a single seam to inject fake plugins.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from paper_search.core.services import Services


@dataclass
class GlobalOpts:
    json_output: bool = False
    quiet: bool = False
    verbose: bool = False
    no_cache: bool = False
    timeout: float | None = None
    config_path: Path | None = None


def configure_logging(opts: GlobalOpts) -> None:
    level = logging.DEBUG if opts.verbose else logging.WARNING
    logging.basicConfig(
        level=level, stream=sys.stderr, format="%(levelname)s %(name)s: %(message)s"
    )


def build_services(opts: GlobalOpts) -> Services:
    """Construct config/cache/http/registry/services from global options."""
    from paper_search.core.cache import Cache
    from paper_search.core.config import load_config
    from paper_search.core.http import HttpClient
    from paper_search.core.plugins import PluginContext, PluginRegistry
    from paper_search.core.services import Services

    config = load_config(opts.config_path)
    if opts.timeout is not None:
        config.general.timeout = opts.timeout
    cache = Cache(enabled=not opts.no_cache)
    http = HttpClient(
        timeout=config.general.timeout,
        mailto=config.general.mailto,
        cache=cache,
    )
    registry = PluginRegistry.discover(PluginContext(config=config, http=http, cache=cache))
    return Services(config=config, cache=cache, registry=registry)
