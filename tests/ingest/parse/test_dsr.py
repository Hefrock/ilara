from __future__ import annotations

from ingest.parse.dsr import decode_rows, where_values


def test_repeat_and_null_bitmasks() -> None:
    rows = [
        {"C": ["Adams", 1], "S": [{"N": "G0"}, {"N": "M0"}]},
        {"C": ["Armstrong", 2]},
        {"C": ["Bedford"], "R": 2},  # M0 repeats Armstrong's 2
        {"C": ["Unk"], "Ø": 2},  # M0 null
        {"G0": "Direct"},
    ]
    out = decode_rows(rows, {})
    assert [(r["G0"], r["M0"]) for r in out] == [
        ("Adams", 1),
        ("Armstrong", 2),
        ("Bedford", 2),
        ("Unk", None),
        ("Direct", None),
    ]


def test_value_dictionary() -> None:
    rows = [{"C": [0, 112], "S": [{"N": "G0", "DN": "D0"}, {"N": "M0"}]}, {"C": [2, 5]}]
    out = decode_rows(rows, {"D0": ["0-4", "5-9", "10-17"]})
    assert [(r["G0"], r["M0"]) for r in out] == [("0-4", 112), ("10-17", 5)]


def test_where_values() -> None:
    pd = (
        '{"queries":[{"Query":{"Commands":[{"SemanticQueryDataShapeCommand":{"Query":'
        '{"Where":[{"Condition":{"In":{"Expressions":[{"Column":{"Property":"TimeFrame"}}],'
        '"Values":[[{"Literal":{"Value":"\'April - Present\'"}}]]}}}]}}}]}}]}'
    )
    assert where_values(pd, "TimeFrame") == ["April - Present"]
    assert where_values(None, "TimeFrame") == []
