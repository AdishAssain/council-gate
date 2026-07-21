from council_gate.parsing import parse, parse_findings


def test_extracts_severity_tagged_lines():
    text = """
    [CRITICAL] auth.py:47 — null deref on expired session
    [P2] some prose nit about naming
    """
    findings = parse_findings(text)
    assert len(findings) == 2
    assert findings[0].severity == "critical"
    assert findings[0].location == "auth.py:47"
    assert findings[1].severity == "minor"


def test_returns_empty_on_unstructured_prose():
    findings = parse_findings("This code looks fine to me overall.")
    assert findings == []


def test_unknown_severity_dropped():
    findings = parse_findings("[FOOBAR] somefile.py — weird thing")
    assert findings == []


def test_json_findings_wrapper():
    text = """{
        "findings": [
            {
                "category": "correctness",
                "severity": "critical",
                "summary": "null deref on expired session",
                "location": "auth.py:47",
                "rationale": "Trips when session expires mid-request.",
                "evidence_quote": "session = cookies.get(...)"
            }
        ]
    }"""
    findings = parse(text)
    assert len(findings) == 1
    assert findings[0].category == "correctness"
    assert findings[0].severity == "critical"
    assert findings[0].location == "auth.py:47"
    assert findings[0].rationale.startswith("Trips")


def test_json_top_level_array():
    text = '[{"severity": "major", "summary": "missing index", "category": "performance"}]'
    findings = parse(text)
    assert len(findings) == 1
    assert findings[0].category == "performance"
    assert findings[0].location is None


def test_json_inside_fenced_block():
    text = """Some preamble prose.
```json
{"findings": [{"severity": "minor", "summary": "naming nit", "category": "nit"}]}
```
trailing commentary."""
    findings = parse(text)
    assert len(findings) == 1
    assert findings[0].summary == "naming nit"


def test_json_inside_plain_fence_no_lang():
    text = """```
[{"severity": "critical", "summary": "race condition", "category": "correctness"}]
```"""
    findings = parse(text)
    assert len(findings) == 1
    assert findings[0].severity == "critical"


def test_json_with_unknown_category_defaults_unspecified():
    text = '[{"severity": "major", "summary": "x", "category": "made_up_category"}]'
    findings = parse(text)
    assert len(findings) == 1
    assert findings[0].category == "unspecified"


def test_json_with_unknown_severity_defaults_minor():
    text = '[{"severity": "moderate", "summary": "x"}]'
    findings = parse(text)
    assert len(findings) == 1
    assert findings[0].severity == "minor"


def test_json_missing_fields_uses_defaults():
    text = '[{"summary": "no severity specified"}]'
    findings = parse(text)
    assert len(findings) == 1
    assert findings[0].severity == "minor"
    assert findings[0].category == "unspecified"
    assert findings[0].rationale == ""
    assert findings[0].evidence_quote is None


def test_malformed_json_returns_empty():
    text = "{this is not: valid json at all"
    assert parse(text) == []


def test_parse_prefers_json_over_legacy():
    text = """[CRITICAL] auth.py:47 — old-style line
```json
{"findings": [{"severity": "critical", "summary": "json finding", "category": "correctness"}]}
```"""
    findings = parse(text)
    assert len(findings) == 1
    assert findings[0].summary == "json finding"


def test_parse_falls_back_to_legacy_when_no_json():
    text = "[CRITICAL] auth.py:47 — legacy line"
    findings = parse(text)
    assert len(findings) == 1
    assert findings[0].severity == "critical"
    assert findings[0].location == "auth.py:47"


def test_parse_returns_empty_for_unstructured():
    findings = parse("Just some prose without structure.")
    assert findings == []
