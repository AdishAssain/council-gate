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

from council_gate.types import Finding, OverallVerdict, Severity

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

_FENCE_RE = re.compile(r"```[a-zA-Z0-9]*\s*(.+?)```", re.DOTALL)


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


def parse(text: str) -> list[Finding]:
    """Findings-only view of parse_review (JSON first, legacy fallback)."""
    return parse_review(text)[0]


def parse_review(text: str) -> tuple[list[Finding], OverallVerdict | None]:
    """Parse both the findings and the (optional) artifact-level `overall`
    verdict from one JSON payload. Falls back to the legacy line parser for
    findings, in which case `overall` is None."""
    for candidate in _json_candidates(text):
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        items = _extract_findings_list(data)
        if items is None:
            continue
        findings = _findings_from_items(items)
        overall = None
        if isinstance(data, dict) and isinstance(data.get("overall"), dict):
            try:
                overall = OverallVerdict.from_dict(data["overall"])
            except (TypeError, ValueError):
                overall = None
        # A dict with a findings key is an answer even when empty (the
        # prompts instruct {"findings": []} for a clean review); a bare list
        # yielding nothing (a stray "[1]" in prose) is not — keep scanning.
        if findings or overall is not None or isinstance(data, dict):
            return findings, overall
    return parse_findings(text), None


def _findings_from_items(items: list[Any]) -> list[Finding]:
    out: list[Finding] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        try:
            out.append(Finding.from_dict(raw))
        except (TypeError, ValueError):
            continue
    return out


_MAX_SLICE_CANDIDATES = 8


def _json_candidates(text: str) -> list[str]:
    """Candidate JSON substrings: fenced blocks first, then full text, then
    balanced {...}/[...] slices in position order."""
    candidates: list[str] = []
    for m in _FENCE_RE.finditer(text):
        candidates.append(m.group(1).strip())
    candidates.append(text.strip())
    candidates.extend(_balanced_slices(text))
    seen: set[str] = set()
    deduped: list[str] = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            deduped.append(c)
    return deduped


def _balanced_slices(text: str) -> list[str]:
    """Balanced {...} / [...] substrings in position order, for JSON wrapped
    in prose. Quote-aware, so brackets inside JSON strings don't truncate."""
    out: list[str] = []
    i = 0
    while i < len(text) and len(out) < _MAX_SLICE_CANDIDATES:
        if text[i] in "{[":
            end = _match_balanced(text, i)
            if end is not None:
                out.append(text[i : end + 1])
                i = end + 1
                continue
        i += 1
    return out


def _match_balanced(text: str, start: int) -> int | None:
    """Index of the close matching text[start] ('{' or '['), skipping string
    contents. Inner pairs of the same type balance out, so counting one
    bracket kind suffices for well-formed JSON."""
    open_ch = text[start]
    close_ch = "}" if open_ch == "{" else "]"
    depth = 0
    in_str = False
    escaped = False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return i
    return None


def _extract_findings_list(data: Any) -> list[Any] | None:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("findings", "issues", "items", "results"):
            val = data.get(key)
            if isinstance(val, list):
                return val
    return None
