"""Table contracts (HANDOFF 4.3). Column order here is the order written to Parquet."""

from __future__ import annotations

import polars as pl

COMMON: dict[str, pl.DataType | type[pl.DataType]] = {
    "jurisdiction": pl.Utf8,
    "disease": pl.Utf8,
    "source_id": pl.Utf8,
    "source_tier": pl.Utf8,
    "as_of_date": pl.Date,
    "fetched_at_utc": pl.Datetime("us", "UTC"),
    "fetched_at_et": pl.Utf8,
    "ingest_run_id": pl.Utf8,
    "raw_sha256": pl.Utf8,
    "seed_file": pl.Utf8,
    "seed_row": pl.Utf8,
    "parser_version": pl.Utf8,
    "source_label": pl.Utf8,
    "source_url": pl.Utf8,
    "url_status": pl.Utf8,
}

_CASE_TAIL = {
    "count_definition": pl.Utf8,
    "date_precision": pl.Utf8,
    "as_of_date_end": pl.Date,
    "is_backfill": pl.Boolean,
    "notes": pl.Utf8,
}

SPECIFIC: dict[str, dict[str, pl.DataType | type[pl.DataType]]] = {
    "case_state": {
        "cum_cases": pl.Int64,
        "counties_with_cases": pl.Int64,
        "hospitalizations": pl.Int64,
        "deaths": pl.Int64,
        "vaccinated_cases": pl.Int64,
        "new_since_count": pl.Int64,
        "new_since_date": pl.Date,
        "new_7day": pl.Int64,
        **_CASE_TAIL,
    },
    "case_county": {
        "county_fips": pl.Utf8,
        "cum_cases": pl.Int64,
        "hospitalizations": pl.Int64,
        "deaths": pl.Int64,
        "community_transmission": pl.Boolean,
        "new_7day": pl.Int64,
        **_CASE_TAIL,
    },
    "immunization_county": {
        "school_year": pl.Utf8,
        "county_fips": pl.Utf8,
        "grade": pl.Utf8,
        "enrolled": pl.Int64,
        "mmr_up_to_date_pct": pl.Float64,
        "med_exempt_pct": pl.Float64,
        "relig_exempt_pct": pl.Float64,
        "philos_exempt_pct": pl.Float64,
        "provisional_pct": pl.Float64,
    },
    "immunization_school": {
        "school_year": pl.Utf8,
        "school_name": pl.Utf8,
        "county_fips": pl.Utf8,
        "grade": pl.Utf8,
        "enrolled": pl.Int64,
        "mmr_pct": pl.Float64,
        "exempt_pcts": pl.Utf8,
        "suppressed_flag": pl.Boolean,
    },
    "vaccine_doses": {
        "period_start": pl.Date,
        "period_end": pl.Date,
        "period_complete": pl.Boolean,
        "doses": pl.Int64,
        "administered_by": pl.Utf8,
        "geography": pl.Utf8,
    },
    "event": {
        "event_id": pl.Utf8,
        "event_type": pl.Utf8,
        "event_date": pl.Date,
        "county_scope": pl.Utf8,
        "title": pl.Utf8,
        "detail": pl.Utf8,
        "date_precision": pl.Utf8,
    },
    "case_demographics": {
        "dimension": pl.Utf8,
        "category": pl.Utf8,
        "cases": pl.Int64,
        "county_fips": pl.Utf8,
        "count_definition": pl.Utf8,
    },
    "wastewater_sample": {
        "sample_id": pl.Utf8,
        "site_id": pl.Utf8,
        "county_fips": pl.Utf8,
        "collection_date": pl.Date,
        "target": pl.Utf8,
        "result": pl.Utf8,
        "concentration": pl.Float64,
    },
    "data_quality_flag": {
        "flag_id": pl.Utf8,
        "raised_utc": pl.Datetime("us", "UTC"),
        "severity": pl.Utf8,
        "code": pl.Utf8,
        "ref_raw_sha256": pl.Utf8,
        "description": pl.Utf8,
        "status": pl.Utf8,
    },
    "quarantine": {
        "table": pl.Utf8,
        "row_json": pl.Utf8,
        "reason_code": pl.Utf8,
        "ref": pl.Utf8,
    },
}

NATURAL_KEYS: dict[str, tuple[str, ...]] = {
    "case_state": ("as_of_date", "source_id", "count_definition"),
    "case_county": ("as_of_date", "source_id", "count_definition", "county_fips"),
    "immunization_county": ("school_year", "county_fips", "grade"),
    "immunization_school": ("school_year", "school_name", "county_fips", "grade"),
    "vaccine_doses": ("as_of_date", "source_id", "administered_by", "geography", "period_start"),
    "event": ("event_id",),
    "wastewater_sample": ("sample_id",),
    "case_demographics": ("as_of_date", "dimension", "category", "county_fips"),
    "data_quality_flag": ("flag_id",),
}

COUNT_DEFINITIONS = ("calendar_year", "since_april", "unknown")
DATE_PRECISIONS = ("exact", "approx", "range", "to_confirm")
EVENT_TYPES = (
    "health_alert",
    "intervention",
    "program",
    "school_calendar",
    "exposure",
    "wastewater_detection",
)
TIERS = ("T1", "T2", "T3", "T3-derived")
FLAG_CODES = (
    "PARSE_SCHEMA_CHANGE",
    "COUNTY_COUNT_DROP",
    "CUM_DECREASE",
    "COUNTY_SUM_MISMATCH",
    "IMPLIED_COUNT_BREAK",
    "STALE_SNAPSHOT",
    "BLOCKED",
    "DEFINITION_UNKNOWN",
    "DATE_TO_CONFIRM",
    "SIZE_BUDGET",
    "HASH_MISMATCH",
    "SOURCE_CONFLICT",
    "DEMOGRAPHIC_SUM_MISMATCH",
)
STORES = ("curated", "sensitivity")


def table_schema(table: str) -> dict[str, pl.DataType | type[pl.DataType]]:
    common = dict(COMMON)
    if table == "event":
        common.pop("as_of_date")
    if table in ("data_quality_flag", "quarantine"):
        # Operational tables: provenance through ingest_run_id and their own refs.
        return {
            "ingest_run_id": pl.Utf8,
            "parser_version": pl.Utf8,
            **SPECIFIC[table],
            "fetched_at_utc": pl.Datetime("us", "UTC"),
        }
    return {**common, **SPECIFIC[table]}


def conform(table: str, df: pl.DataFrame) -> pl.DataFrame:
    """Add missing nullable columns, cast, and order columns to the contract."""
    sch = table_schema(table)
    if df.width == 0:
        return pl.DataFrame(schema=sch)
    extra = set(df.columns) - set(sch)
    if extra:
        raise ValueError(f"{table}: unexpected columns {sorted(extra)}")
    cols = []
    for name, dtype in sch.items():
        if name in df.columns:
            if dtype == pl.Date and df.schema[name] == pl.String:
                cols.append(pl.col(name).str.to_date("%Y-%m-%d").alias(name))
            else:
                cols.append(pl.col(name).cast(dtype))
        else:
            cols.append(pl.lit(None, dtype=dtype).alias(name))
    return df.select(cols)
