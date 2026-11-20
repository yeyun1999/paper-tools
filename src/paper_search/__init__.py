"""paper-search: literature search and open-access full-text retrieval CLI."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("paper-search")
except PackageNotFoundError:  # pragma: no cover - running from source without install
    __version__ = "0.0.0"
