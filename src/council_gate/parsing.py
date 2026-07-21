"""Parse model review text into structured Findings.

Two parser strategies, tried in order:
1. JSON — preferred. Models receive a schema in the prompt and return
   {"findings": [{...}, ...]} or a top-level array.
2. Legacy regex — fallback. Matches severity-tagged lines like
   `[CRITICAL] foo/bar.py:42 — description`. Kept so a model that
   ignores the JSON instruction still produces something usable.

If both fail, returns []; the gate falls back to Review.raw_text.
"""
import json
import logging
import re
from typing import Any

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

_FENCE_RE = re.compile(r"```(?:json)?\s*(.+?)```", re.DOTALL | re.IGNORECASE)


def parse_findings(text: str) -> list[Finding]:
    """Legacy severity-tagged-line parser. Kept as fallback."""
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
        log.debug(
            "parse_findings: no severity-tagged lines found (%d chars input)", len(text)
        )
    return out


def parse_findings_json(text: str) -> list[Finding]:
    """Extract Findings from a JSON payload anywhere in the text.

    Accepts:
      - {"findings": [...]}
      - top-level array [...]
      - JSON inside ```json``` or plain ``` fences
    Malformed JSON returns []; the caller should fall back.
    """
    for candidate in _json_candidates(text):
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        items = _extract_findings_list(data)
        if items is None:
            continue
        out: list[Finding] = []
        for raw in items:
            if not isinstance(raw, dict):
                continue
            try:
                out.append(Finding.from_dict(raw))
            except (TypeError, ValueError):
                continue
        if out:
            return out
    return []


def parse(text: str) -> list[Finding]:
    """Try JSON first, then legacy regex."""
    findings = parse_findings_json(text)
    if findings:
        return findings
    return parse_findings(text)


def _json_candidates(text: str) -> list[str]:
    """Yield candidate JSON substrings: fenced blocks first, then full text,
    then a best-effort slice from first { or [ to matching close."""
    candidates: list[str] = []
    for m in _FENCE_RE.finditer(text):
        candidates.append(m.group(1).strip())
    candidates.append(text.strip())
    sliced = _slice_outer_json(text)
    if sliced:
        candidates.append(sliced)
    seen: set[str] = set()
    deduped: list[str] = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            deduped.append(c)
    return deduped


def _slice_outer_json(text: str) -> str | None:
    """Return the substring from the first { or [ to its matching close.
    Naive — doesn't handle strings with braces — but a useful fallback when
    a model wraps JSON in prose."""
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = text.find(open_ch)
        if start < 0:
            continue
        depth = 0
        for i in range(start, len(text)):
            if text[i] == open_ch:
                depth += 1
            elif text[i] == close_ch:
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
    return None


def _extract_findings_list(data: Any) -> list[Any] | None:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("findings", "issues", "items", "results"):
            if isinstance(data.get(key), list):
                return data[key]
    return None
