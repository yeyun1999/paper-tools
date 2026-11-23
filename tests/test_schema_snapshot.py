"""Schema 1.0 freeze: snapshot gate for the machine-readable JSON contract.

Any change to model fields, envelope structure, or schema_version fails this
suite. If a change is intentional: regenerate the snapshot, record it in
CHANGELOG, and treat it as a breaking change (bump schema_version) now that
1.0 is frozen.

Regenerate: uv run python -c "from tests.test_schema_snapshot import write_snapshot as w; w()"
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paper_tools.cli import render
from paper_tools.cli.schema import _MODELS
from paper_tools.core.errors import UsageError

SNAPSHOT_PATH = Path(__file__).parent / "snapshots" / "schema_v1.json"


def current_snapshot() -> dict[str, Any]:
    return {
        "schema_version": render.SCHEMA_VERSION,
        "success_envelope": render.success_envelope("cmd", {}, []),
        "error_envelope": render.error_envelope(UsageError("example")),
        "models": {name: model.model_json_schema() for name, model in _MODELS.items()},
    }


def write_snapshot() -> None:
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(
        json.dumps(current_snapshot(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_schema_version_frozen() -> None:
    assert render.SCHEMA_VERSION == "1.0"


def test_contract_snapshot_matches() -> None:
    expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    actual = json.loads(json.dumps(current_snapshot(), sort_keys=True))
    assert actual == expected, (
        "JSON contract changed against the frozen 1.0 snapshot. "
        "If intentional: update CHANGELOG, bump schema_version, and regenerate "
        "tests/snapshots/schema_v1.json (see module docstring)."
    )
