"""Form fields: disposition, confidence, and the per-review overall verdict."""
from council_gate.parsing import parse_review
from council_gate.types import Finding, OverallVerdict, Review


def test_finding_new_fields_default():
    f = Finding(severity="major", summary="x")
    assert f.disposition == "defect"
    assert f.confidence is None


def test_finding_from_dict_parses_new_fields():
    f = Finding.from_dict(
        {"severity": "critical", "summary": "boom", "disposition": "risk", "confidence": "high"}
    )
    assert f.disposition == "risk"
    assert f.confidence == "high"


def test_finding_from_dict_defaults_invalid_new_fields():
    f = Finding.from_dict(
        {"severity": "minor", "summary": "s", "disposition": "nonsense", "confidence": "kinda"}
    )
    assert f.disposition == "defect"  # invalid -> default
    assert f.confidence is None  # invalid -> None


def test_finding_to_dict_roundtrips_new_fields():
    f = Finding(severity="nit", summary="s", disposition="endorse", confidence="low")
    d = f.to_dict()
    assert d["disposition"] == "endorse"
    assert d["confidence"] == "low"
    assert Finding.from_dict(d).disposition == "endorse"


def test_overall_verdict_from_dict():
    o = OverallVerdict.from_dict(
        {"recommendation": "block", "severity": "critical", "rationale": "bad"}
    )
    assert o.recommendation == "block"
    assert o.severity == "critical"
    assert o.rationale == "bad"


def test_overall_verdict_defaults_invalid():
    o = OverallVerdict.from_dict({"recommendation": "nope", "severity": "nope"})
    assert o.recommendation == "revise"  # invalid -> neutral default
    assert o.severity == "minor"  # invalid -> default


def test_review_overall_defaults_none():
    r = Review(model_id="m", provider="p", findings=[])
    assert r.overall is None


def test_parse_review_extracts_findings_and_overall():
    text = """{
      "overall": {"recommendation": "revise", "severity": "major", "rationale": "mixed"},
      "findings": [
        {"summary": "a", "severity": "major", "disposition": "defect", "confidence": "high"}
      ]
    }"""
    findings, overall = parse_review(text)
    assert len(findings) == 1
    assert findings[0].disposition == "defect"
    assert overall is not None
    assert overall.recommendation == "revise"
    assert overall.severity == "major"


def test_parse_review_without_overall_returns_none():
    findings, overall = parse_review('{"findings": [{"summary": "a", "severity": "minor"}]}')
    assert len(findings) == 1
    assert overall is None


def test_parse_review_legacy_lines_returns_none_overall():
    findings, overall = parse_review("[CRITICAL] foo.py:1 — broken")
    assert len(findings) == 1
    assert findings[0].severity == "critical"
    assert overall is None


def test_parse_review_clean_review_preserves_overall():
    # The prompts instruct exactly this shape for a no-issues review.
    text = """{
      "overall": {"recommendation": "accept", "severity": "nit", "rationale": "solid"},
      "findings": []
    }"""
    findings, overall = parse_review(text)
    assert findings == []
    assert overall is not None
    assert overall.recommendation == "accept"


def test_parse_review_prose_wrapped_top_level_array():
    text = 'Here are my findings:\n[{"summary": "a", "severity": "minor"}]'
    findings, overall = parse_review(text)
    assert len(findings) == 1
    assert findings[0].summary == "a"
    assert overall is None


def test_finding_from_dict_unhashable_values_default():
    f = Finding.from_dict(
        {
            "severity": ["critical"],
            "summary": "x",
            "category": {"a": 1},
            "disposition": [],
            "confidence": {},
            "location": {"file": "a.py"},
            "evidence_quote": ["q"],
        }
    )
    assert f.severity == "minor"
    assert f.category == "unspecified"
    assert f.disposition == "defect"
    assert f.confidence is None
    assert f.location is None
    assert f.evidence_quote is None


def test_overall_verdict_from_dict_unhashable_values_default():
    o = OverallVerdict.from_dict({"recommendation": ["block"], "severity": {}})
    assert o.recommendation == "revise"
    assert o.severity == "minor"


def test_parse_review_prose_bracket_before_json_object():
    # A bracketed citation parses as a JSON list; it must not mask the
    # real payload that follows.
    text = 'Based on [1], my review:\n{"findings": [{"summary": "a", "severity": "minor"}]}'
    findings, overall = parse_review(text)
    assert len(findings) == 1
    assert findings[0].summary == "a"


def test_parse_review_braces_inside_json_strings():
    text = '{"findings": [{"summary": "dict {a: 1} leaks", "severity": "minor", "evidence_quote": "x = {\\"k\\": [1]}"}]}'
    findings, _ = parse_review("Review:\n" + text)
    assert len(findings) == 1
    assert "leaks" in findings[0].summary


def test_parse_empty_json_findings_does_not_invoke_legacy():
    # A valid empty review must not have findings fabricated from prose.
    text = 'Earlier I wrote [CRITICAL] foo.py:1 — bad\n\n{"findings": []}'
    from council_gate.parsing import parse

    assert parse(text) == []


def test_enum_fields_case_insensitive():
    f = Finding.from_dict(
        {"severity": "CRITICAL", "summary": "x", "disposition": "Defect", "confidence": "HIGH"}
    )
    assert f.severity == "critical"
    assert f.disposition == "defect"
    assert f.confidence == "high"
    o = OverallVerdict.from_dict({"recommendation": "Block", "severity": "Major"})
    assert o.recommendation == "block"
    assert o.severity == "major"


def test_review_json_schema_strict_eligible():
    from council_gate.types import review_json_schema

    schema = review_json_schema()

    def check(obj):
        assert obj["additionalProperties"] is False
        assert set(obj["required"]) == set(obj["properties"])

    check(schema)
    check(schema["properties"]["findings"]["items"])
    check(schema["properties"]["overall"])
    finding = schema["properties"]["findings"]["items"]["properties"]
    assert list(finding) == [
        "location", "evidence_quote", "summary", "rationale",
        "category", "disposition", "severity", "confidence",
    ]
    assert "unspecified" not in finding["category"]["enum"]
    assert list(schema["properties"]) == ["findings", "overall"]
