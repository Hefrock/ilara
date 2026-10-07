"""County name normalisation and crosswalk (T1.4)."""

from __future__ import annotations

import re
import unicodedata

_SUFFIX = re.compile(r"\b(county|cnty|co)\b\.?", re.IGNORECASE)


def normalize_name(name: str) -> str:
    """'McKean County' / 'Mc Kean Co.' / 'MCKEAN' all become 'mckean'."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = s.lower().replace("&", "and")
    s = _SUFFIX.sub(" ", s)
    s = re.sub(r",?\s*(pa|pennsylvania)$", "", s.strip())
    return re.sub(r"[^a-z]", "", s)


def variants(name: str) -> set[str]:
    base = name.strip()
    forms = {
        base,
        f"{base} County",
        f"{base} Co.",
        f"{base} Co",
        base.upper(),
        f"{base.upper()} COUNTY",
        f"{base}, PA",
        f"{base} County, Pennsylvania",
    }
    return {normalize_name(f) for f in forms}


def build(counties: dict[str, str], extra: dict[str, str] | None = None) -> dict[str, str]:
    """Map normalised variant -> FIPS. Raises on any collision."""
    out: dict[str, str] = {}
    items = [(fips, v) for fips, name in counties.items() for v in variants(name)]
    items += [(fips, normalize_name(v)) for v, fips in (extra or {}).items()]
    for fips, v in items:
        if not v:
            raise ValueError(f"empty normalised variant for {fips}")
        if out.get(v, fips) != fips:
            raise ValueError(f"crosswalk collision: {v!r} -> {out[v]} and {fips}")
        out[v] = fips
    return out


def resolve(name: str, xwalk: dict[str, str]) -> str:
    key = normalize_name(name)
    if key not in xwalk:
        raise KeyError(f"county name {name!r} (normalised {key!r}) not in crosswalk")
    return xwalk[key]
