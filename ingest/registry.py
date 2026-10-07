"""Source registry loader (HANDOFF 4.2)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from ingest import paths

Tier = Literal["T1", "T2", "T3", "T3-derived"]
AccessPath = Literal["browser", "http", "seed", "manual", "none"]


class Source(BaseModel):
    source_id: str
    name: str
    url: str | None
    url_status: str
    tier: Tier
    cadence: str
    access_path: AccessPath
    ext: str
    robots_checked_utc: str | None = None
    terms_note: str | None = None
    last_verified_utc: str | None = None
    notes: str | None = None

    @property
    def capturable(self) -> bool:
        return self.access_path in ("browser", "http") and bool(self.url)


def load(root: Path | None = None) -> dict[str, Source]:
    raw = yaml.safe_load(paths.registry_path(root).read_text())
    out: dict[str, Source] = {}
    for item in raw["sources"]:
        s = Source.model_validate(item)
        if s.source_id in out:
            raise ValueError(f"duplicate source_id {s.source_id}")
        out[s.source_id] = s
    return out
