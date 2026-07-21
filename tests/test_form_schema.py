"""Phase-1 canonical form additions: disposition, confidence, overall verdict."""
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
