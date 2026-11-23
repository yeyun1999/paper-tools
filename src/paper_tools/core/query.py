"""Unified query model: structured fields (portable) + raw native passthrough."""

from __future__ import annotations

from pydantic import BaseModel, model_validator


class Query(BaseModel):
    text: str | None = None
    title: str | None = None
    author: str | None = None
    journal: str | None = None
    year_from: int | None = None
    year_to: int | None = None
    open_access: bool | None = None
    raw: str | None = None

    @model_validator(mode="after")
    def _validate_query(self) -> Query:
        structured = (
            self.text,
            self.title,
            self.author,
            self.journal,
            self.year_from,
            self.year_to,
            self.open_access,
        )
        has_structured = any(v is not None for v in structured)
        if self.raw is not None and has_structured:
            raise ValueError("--raw is mutually exclusive with structured query fields")
        if self.raw is None and not has_structured:
            raise ValueError("empty query: provide search text or structured fields")
        if (
            self.year_from is not None
            and self.year_to is not None
            and self.year_from > self.year_to
        ):
            raise ValueError("year_from must not be greater than year_to")
        return self
