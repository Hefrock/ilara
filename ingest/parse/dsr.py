"""Decoder for Power BI ``querydata`` results (the "DSR" data shape).

Rows are lists of dicts. The first row of a block carries ``S``, the column schema (``N``
name, ``DN`` optional value-dictionary). Each row then gives its values in ``C`` in schema
order, skipping columns flagged in two bitmasks: ``R`` (bit i set: column i repeats the
previous row's value) and ``Ø`` (bit i set: column i is null). A row may also carry values
directly under the column name (``{"G0": "Adams"}``). Dictionary-coded columns hold an index
into ``ValueDicts``.
"""

from __future__ import annotations

from typing import Any

NULL_KEY = "Ø"


def decode_rows(rows: list[dict[str, Any]], dicts: dict[str, list[Any]]) -> list[dict[str, Any]]:
    schema: list[dict[str, Any]] | None = None
    prev: dict[str, Any] = {}
    out: list[dict[str, Any]] = []
    for row in rows:
        if "S" in row:
            schema = row["S"]
        if schema is None:
            raise ValueError("DSR row before any schema")
        values = iter(row.get("C", []))
        repeat, null = int(row.get("R", 0)), int(row.get(NULL_KEY, 0))
        cur: dict[str, Any] = {}
        for i, col in enumerate(schema):
            name = col["N"]
            if name in row:
                v = row[name]
            elif repeat >> i & 1:
                cur[name] = prev.get(name)
                continue
            elif null >> i & 1:
                cur[name] = None
                continue
            else:
                v = next(values, None)
            if col.get("DN") and isinstance(v, int):
                v = dicts[col["DN"]][v]
            cur[name] = v
        out.append(cur)
        prev = cur
    return out


def decode_result(body: dict[str, Any]) -> dict[str, Any]:
    """Return ``{"select": [descriptor...], "blocks": {"DM0": [row...], ...}}`` with rows keyed
    by the descriptor ``Name`` (for example ``Sum(PAmeasles2026_Public.count)``)."""
    data = body["results"][0]["result"]["data"]
    select = data["descriptor"]["Select"]
    by_key = {s["Value"]: s["Name"] for s in select}
    ds = data["dsr"]["DS"][0]
    dicts = ds.get("ValueDicts", {})
    blocks: dict[str, list[dict[str, Any]]] = {}
    for ph in ds.get("PH", []):
        for block, rows in ph.items():
            decoded = decode_rows(rows, dicts)
            blocks[block] = [{by_key.get(k, k): v for k, v in r.items()} for r in decoded]
    return {"select": select, "blocks": blocks}


def where_values(post_data: str | None, prop: str) -> list[str]:
    """Literal values a query filters ``prop`` on (for example the TimeFrame slicer)."""
    import json

    if not post_data:
        return []
    q = json.loads(post_data)["queries"][0]["Query"]["Commands"][0][
        "SemanticQueryDataShapeCommand"
    ]["Query"]
    out: list[str] = []
    for w in q.get("Where", []) or []:
        cond = w.get("Condition", {}).get("In", {})
        exprs = cond.get("Expressions", [])
        if any(e.get("Column", {}).get("Property") == prop for e in exprs):
            for vals in cond.get("Values", []):
                for v in vals:
                    out.append(str(v["Literal"]["Value"]).strip("'"))
    return out
