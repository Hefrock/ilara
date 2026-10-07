"""Case-level safeguard for dashboard captures (owner decision B16, I10).

The dashboard's published data model holds one row per case (``CaseNo``) and per vaccination
record (``record_id``). The visible pages show only aggregates. A response is refused (never
saved) when identifier *values* could be in it:

- a data query that selects or groups by an identifier column outside an aggregation
  (``Count(CaseNo)`` is an aggregate and allowed; ``CaseNo`` itself is not), or whose query
  cannot be parsed;
- any response whose result descriptor names a bare identifier column.

Metadata that only lists column names (the field list, the report definition) is allowed:
it contains no case data. The capture never opens hidden pages or builds its own queries;
this check is the second line of defence.
"""

from __future__ import annotations

import json
from typing import Any

CASE_KEYS = frozenset({"CaseNo", "record_id"})


def _is_data_query(url: str, post_data: str | None) -> bool:
    return "querydata" in url.lower() or (
        post_data is not None and "SemanticQueryDataShapeCommand" in post_data
    )


def _bare_identifier_column(obj: Any, inside_aggregation: bool = False) -> bool:
    if isinstance(obj, dict):
        for key, val in obj.items():
            agg = inside_aggregation or key in ("Aggregation", "Measure")
            if (
                key == "Column"
                and not inside_aggregation
                and isinstance(val, dict)
                and val.get("Property") in CASE_KEYS
            ):
                return True
            if _bare_identifier_column(val, agg):
                return True
    elif isinstance(obj, list):
        return any(_bare_identifier_column(v, inside_aggregation) for v in obj)
    return False


def _descriptor_names_identifier(obj: Any) -> bool:
    if isinstance(obj, dict):
        name = obj.get("Name")
        if (
            isinstance(name, str)
            and "(" not in name
            and "." in name
            and name.rsplit(".", 1)[-1] in CASE_KEYS
        ):
            return True
        return any(_descriptor_names_identifier(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_descriptor_names_identifier(v) for v in obj)
    return False


def refusal_reason(url: str, post_data: str | None, body: Any) -> str | None:
    """Return why a response must not be saved, or None when it is safe."""
    if _is_data_query(url, post_data):
        try:
            query = json.loads(post_data) if post_data else None
        except ValueError:
            return "case-level check: data query could not be parsed"
        if query is None:
            return "case-level check: data query without a request body"
        if _bare_identifier_column(query):
            return "case-level: query selects an identifier column"
    if _descriptor_names_identifier(body):
        return "case-level: result names an identifier column"
    return None
