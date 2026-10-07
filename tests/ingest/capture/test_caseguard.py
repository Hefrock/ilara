from __future__ import annotations

import json

from ingest.capture.caseguard import refusal_reason

QD = "https://wabi-us-gov-iowa-api.analysis.usgovcloudapi.net/public/reports/querydata"


def _query(select: list[dict]) -> str:
    return json.dumps(
        {
            "queries": [
                {
                    "Query": {
                        "Commands": [
                            {
                                "SemanticQueryDataShapeCommand": {
                                    "Query": {
                                        "From": [{"Name": "p", "Entity": "PAmeasles2026_Public"}],
                                        "Select": select,
                                    }
                                }
                            }
                        ]
                    }
                }
            ]
        }
    )


def col(prop: str) -> dict:
    return {
        "Column": {"Expression": {"SourceRef": {"Source": "p"}}, "Property": prop},
        "Name": f"PAmeasles2026_Public.{prop}",
    }


def test_aggregate_query_allowed() -> None:
    q = _query(
        [
            col("County"),
            {
                "Aggregation": {"Expression": col("CaseNo"), "Function": 2},
                "Name": "Count(PAmeasles2026_Public.CaseNo)",
            },
        ]
    )
    body = {
        "results": [
            {
                "result": {
                    "data": {
                        "descriptor": {
                            "Select": [
                                {"Name": "PAmeasles2026_Public.County"},
                                {"Name": "Count(PAmeasles2026_Public.CaseNo)"},
                            ]
                        }
                    }
                }
            }
        ]
    }
    assert refusal_reason(QD, q, body) is None


def test_identifier_column_refused() -> None:
    assert refusal_reason(QD, _query([col("CaseNo"), col("County")]), {}) is not None
    mmr = _query([col("record_id")])
    assert "identifier" in (refusal_reason(QD, mmr, {}) or "")


def test_descriptor_identifier_refused_even_without_query() -> None:
    body = {"descriptor": {"Select": [{"Name": "PAmeasles2026_Public_mmr.record_id"}]}}
    assert refusal_reason("https://x.test/other", None, body) is not None


def test_unparseable_data_query_refused() -> None:
    assert refusal_reason(QD, "not json", {}) is not None
    assert refusal_reason(QD, None, {}) is not None


def test_metadata_listing_column_names_allowed() -> None:
    schema = {
        "schemas": [
            {
                "schema": {
                    "Entities": [
                        {
                            "Name": "PAmeasles2026_Public",
                            "Properties": [{"Name": "CaseNo"}, {"Name": "County"}],
                        }
                    ]
                }
            }
        ]
    }
    assert (
        refusal_reason(
            "https://x.test/public/reports/conceptualschema", '{"modelIds": [1]}', schema
        )
        is None
    )
