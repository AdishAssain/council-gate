from council_gate.parsing import parse_findings


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
