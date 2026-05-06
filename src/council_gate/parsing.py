"""Parse model review text into structured Findings.

v0: regex extraction of severity-tagged lines like
    `[CRITICAL] foo/bar.py:42 — description`.
Models that return free prose without that shape get an empty finding list
and the raw text on `Review.raw_text` for the gate to fall back on.
Upgrade path: ask each adapter to emit JSON.
"""
import logging
import re

from council_gate.types import Finding, Severity

log = logging.getLogger(__name__)

_SEVERITY_MAP: dict[str, Severity] = {
    "critical": "critical",
    "p0": "critical",
    "major": "major",
    "p1": "major",
    "minor": "minor",
    "p2": "minor",
    "p3": "nit",
    "nit": "nit",
}

_LINE_RE = re.compile(
    r"^\s*\[(?P<sev>[a-zA-Z0-9]+)\]\s*(?:(?P<loc>[^\s—\-:]+(?::\d+)?)\s*[—\-:]\s*)?(?P<desc>.+?)\s*$",
    re.MULTILINE,
)


def parse_findings(text: str) -> list[Finding]:
    out: list[Finding] = []
    for m in _LINE_RE.finditer(text):
        sev_raw = m.group("sev").lower()
        sev = _SEVERITY_MAP.get(sev_raw)
        if sev is None:
            continue
        out.append(
            Finding(severity=sev, summary=m.group("desc"), location=m.group("loc"))
        )
    if not out:
        log.warning(
            "parse_findings: no severity-tagged lines found (%d chars input)", len(text)
        )
    return out
