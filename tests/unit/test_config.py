"""Unit tests: config loading, precedence, env overrides, writing."""

from __future__ import annotations

from pathlib import Path

import pytest

from paper_tools.core.config import (
    load_config,
    mask_secrets,
    set_config_value,
)
from paper_tools.core.errors import UsageError


def test_defaults() -> None:
    config = load_config(Path("/nonexistent/config.toml"))
    assert config.general.default_source == "pubmed"
    assert config.general.timeout == 30.0
    assert config.fetch.output is None


def test_file_loading(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        '[general]\ndefault_source = "europepmc"\n[plugins.unpaywall]\nemail = "a@b.org"\n',
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.general.default_source == "europepmc"
    assert config.plugin_config("unpaywall")["email"] == "a@b.org"


def test_env_overrides_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[general]\ntimeout = 10\n", encoding="utf-8")
    monkeypatch.setenv("PAPER_TOOLS_TIMEOUT", "99")
    monkeypatch.setenv("PAPER_TOOLS_SEMANTIC_SCHOLAR__API_KEY", "secret123")
    config = load_config(path)
    assert config.general.timeout == 99.0
    assert config.plugin_config("semantic_scholar")["api_key"] == "secret123"


def test_set_and_reload(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    set_config_value("plugins.unpaywall.email", "me@lab.org", path)
    set_config_value("general.timeout", "45", path)
    config = load_config(path)
    assert config.plugin_config("unpaywall")["email"] == "me@lab.org"
    assert config.general.timeout == 45.0


def test_set_invalid_key(tmp_path: Path) -> None:
    with pytest.raises(UsageError):
        set_config_value("bogus.key", "x", tmp_path / "c.toml")


def test_set_invalid_value(tmp_path: Path) -> None:
    with pytest.raises(UsageError):
        set_config_value("general.timeout", "not-a-number", tmp_path / "c.toml")


def test_mask_secrets() -> None:
    data = {"plugins": {"pubmed": {"api_key": "abc", "tool": "x"}}}
    masked = mask_secrets(data)
    assert masked["plugins"]["pubmed"]["api_key"] == "***"
    assert masked["plugins"]["pubmed"]["tool"] == "x"
