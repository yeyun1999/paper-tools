"""Shared row -> Paper mapping for the example API.

Replace ``_row_to_paper`` fields with your source's response shape.
Identifier normalization helpers live in ``paper_tools.core.models``.
"""

from __future__ import annotations

from typing import Any

from paper_tools.core.models import Author, Paper, normalize_doi


def row_to_paper(row: dict[str, Any]) -> Paper:
    identifiers: dict[str, str] = {}
    if row.get("doi"):
        identifiers["doi"] = normalize_doi(str(row["doi"]))
    if row.get("pmid"):
        identifiers["pmid"] = str(row["pmid"])
    return Paper(
        title=str(row.get("title") or ""),
        identifiers=identifiers,
        authors=[Author(name=str(a["name"])) for a in row.get("authors", []) if a.get("name")],
        year=row.get("year"),
        journal=row.get("journal"),
        abstract=row.get("abstract"),
        oa_status=row.get("oa_status") or "unknown",
        license=row.get("license"),
        publisher_url=row.get("url"),
    )
