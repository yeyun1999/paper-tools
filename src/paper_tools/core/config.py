"""Configuration: TOML file < environment variables < CLI options.

Plugin env override convention: ``PAPER_TOOLS_<PLUGIN>__<KEY>`` (double
underscore separates plugin namespace from option), e.g.
``PAPER_TOOLS_SEMANTIC_SCHOLAR__API_KEY``.
"""

from __future__ import annotations

import contextlib
import os
import tomllib
from pathlib import Path
from typing import Any

import platformdirs
import tomli_w
from pydantic import BaseModel, Field, ValidationError

from paper_tools.core.errors import ConfigError, UsageError
from paper_tools.core.models import ArtifactFormat

_ENV_PREFIX = "PAPER_TOOLS_"
_SECRET_HINTS = ("key", "token", "secret")
_DEFAULT_FORMAT_PRIORITY: list[ArtifactFormat] = ["pdf", "xml", "text"]


class GeneralConfig(BaseModel):
    default_source: str = "pubmed"
    timeout: float = 30.0
    mailto: str | None = None


class FetchConfig(BaseModel):
    format_priority: list[ArtifactFormat] = Field(
        default_factory=lambda: list(_DEFAULT_FORMAT_PRIORITY)
    )
    out_dir: str = "./papers"
    locators: list[str] = Field(default_factory=list)  # empty = all registered locators


class MetadataConfig(BaseModel):
    enrich_priority: list[str] = Field(
        default_factory=lambda: [
            "pubmed",
            "europepmc",
            "crossref",
            "openalex",
            "semantic_scholar",
            "unpaywall",
        ]
    )


class AppConfig(BaseModel):
    general: GeneralConfig = Field(default_factory=GeneralConfig)
    fetch: FetchConfig = Field(default_factory=FetchConfig)
    metadata: MetadataConfig = Field(default_factory=MetadataConfig)
    plugins: dict[str, dict[str, Any]] = Field(default_factory=dict)

    def plugin_config(self, name: str) -> dict[str, Any]:
        return self.plugins.get(name, {})


def default_config_path() -> Path:
    return Path(platformdirs.user_config_dir("paper-tools", appauthor=False)) / "config.toml"


def load_config(path: Path | None = None) -> AppConfig:
    env_path = os.environ.get(f"{_ENV_PREFIX}CONFIG")
    config_path = path or (Path(env_path) if env_path else default_config_path())
    data: dict[str, Any] = {}
    if config_path.exists():
        try:
            data = tomllib.loads(config_path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"Invalid TOML in {config_path}: {exc}") from exc
    try:
        config = AppConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"Invalid configuration in {config_path}: {exc}") from exc
    _apply_env(config)
    return config


def _apply_env(config: AppConfig) -> None:
    general_map = {
        "default_source": "default_source",
        "timeout": "timeout",
        "mailto": "mailto",
    }
    for env_key, value in os.environ.items():
        if not env_key.startswith(_ENV_PREFIX):
            continue
        rest = env_key[len(_ENV_PREFIX) :].lower()
        if rest == "config":
            continue
        if rest in general_map:
            field = general_map[rest]
            if field == "timeout":
                try:
                    setattr(config.general, field, float(value))
                except ValueError as exc:
                    raise ConfigError(f"{env_key} must be a number") from exc
            else:
                setattr(config.general, field, value)
        elif "__" in rest:
            plugin, _, option = rest.partition("__")
            if plugin and option:
                config.plugins.setdefault(plugin, {})[option] = value


def config_path_for_write(path: Path | None = None) -> Path:
    env_path = os.environ.get(f"{_ENV_PREFIX}CONFIG")
    return path or (Path(env_path) if env_path else default_config_path())


def set_config_value(key: str, raw_value: str, path: Path | None = None) -> Path:
    """Set a dotted key in the TOML file (env overrides are not written)."""
    parts = key.split(".")
    if parts[0] not in {"general", "fetch", "metadata", "plugins"} or len(parts) < 2:
        raise UsageError(
            f"Invalid config key {key!r}; expected general.*, fetch.*, metadata.*, plugins.*.*"
        )
    config_path = config_path_for_write(path)
    data: dict[str, Any] = {}
    if config_path.exists():
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    value: Any = raw_value
    with contextlib.suppress(tomllib.TOMLDecodeError):
        value = tomllib.loads(f"value = {raw_value}")["value"]
    node = data
    for part in parts[:-1]:
        child = node.setdefault(part, {})
        if not isinstance(child, dict):
            raise UsageError(f"Config key {key!r} conflicts with a non-table value.")
        node = child
    node[parts[-1]] = value
    try:
        AppConfig.model_validate(data)
    except ValidationError as exc:
        raise UsageError(f"Invalid value for {key!r}: {exc}") from exc
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(tomli_w.dumps(data), encoding="utf-8")
    return config_path


def mask_secrets(data: dict[str, Any]) -> dict[str, Any]:
    masked: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            masked[key] = mask_secrets(value)
        elif any(hint in key.lower() for hint in _SECRET_HINTS):
            masked[key] = "***"
        else:
            masked[key] = value
    return masked
