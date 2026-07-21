from dataclasses import dataclass, field
from typing import Any, Literal

Severity = Literal["critical", "major", "minor", "nit"]

Category = Literal[
    "correctness",
    "missing_evidence",
    "method_gap",
    "edge_case",
    "missing_data_handling",
    "security",
    "performance",
    "clarity",
    "scope",
    "novelty",
    "reproducibility",
    "nit",
    "unspecified",
]

# Phase-1 canonical form additions.
# disposition: the KIND of claim, so the gate can tell a raised concern from an
#   explicit endorsement (and, later, a contradiction from mere divergence).
# confidence: the reviewer's own certainty, for weighting.
# recommendation: a per-reviewer artifact-level stance — a clean top-level
#   agree/disagree signal that complements finding-level agreement.
Disposition = Literal["defect", "risk", "gap", "question", "endorse"]
Confidence = Literal["low", "med", "high"]
Recommendation = Literal["block", "revise", "accept"]

_VALID_SEVERITIES: frozenset[str] = frozenset(("critical", "major", "minor", "nit"))
_VALID_CATEGORIES: frozenset[str] = frozenset(
    (
        "correctness",
        "missing_evidence",
        "method_gap",
        "edge_case",
        "missing_data_handling",
        "security",
        "performance",
        "clarity",
        "scope",
        "novelty",
        "reproducibility",
        "nit",
        "unspecified",
    )
)
_VALID_DISPOSITIONS: frozenset[str] = frozenset(
    ("defect", "risk", "gap", "question", "endorse")
)
_VALID_CONFIDENCES: frozenset[str] = frozenset(("low", "med", "high"))
_VALID_RECOMMENDATIONS: frozenset[str] = frozenset(("block", "revise", "accept"))


@dataclass(slots=True, frozen=True)
class Finding:
    severity: Severity
    summary: str
    location: str | None = None
    category: Category = "unspecified"
    rationale: str = ""
    evidence_quote: str | None = None
    disposition: Disposition = "defect"
    confidence: Confidence | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "summary": self.summary,
            "location": self.location,
            "category": self.category,
            "rationale": self.rationale,
            "evidence_quote": self.evidence_quote,
            "disposition": self.disposition,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Finding":
        sev = d.get("severity", "minor")
        if sev not in _VALID_SEVERITIES:
            sev = "minor"
        cat = d.get("category", "unspecified")
        if cat not in _VALID_CATEGORIES:
            cat = "unspecified"
        disp = d.get("disposition", "defect")
        if disp not in _VALID_DISPOSITIONS:
            disp = "defect"
        conf = d.get("confidence")
        if conf not in _VALID_CONFIDENCES:
            conf = None
        return cls(
            severity=sev,  # type: ignore[arg-type]
            summary=str(d.get("summary", "")).strip(),
            location=d.get("location") or None,
            category=cat,  # type: ignore[arg-type]
            rationale=str(d.get("rationale", "")).strip(),
            evidence_quote=d.get("evidence_quote") or None,
            disposition=disp,  # type: ignore[arg-type]
            confidence=conf,  # type: ignore[arg-type]
        )


@dataclass(slots=True, frozen=True)
class OverallVerdict:
    """A reviewer's artifact-level stance, distinct from its findings."""

    recommendation: Recommendation
    severity: Severity
    rationale: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "OverallVerdict":
        rec = d.get("recommendation", "revise")
        if rec not in _VALID_RECOMMENDATIONS:
            rec = "revise"
        sev = d.get("severity", "minor")
        if sev not in _VALID_SEVERITIES:
            sev = "minor"
        return cls(
            recommendation=rec,  # type: ignore[arg-type]
            severity=sev,  # type: ignore[arg-type]
            rationale=str(d.get("rationale", "")).strip(),
        )


@dataclass(slots=True)
class Review:
    model_id: str
    provider: str
    findings: list[Finding] = field(default_factory=list)
    raw_text: str = ""
    error: str | None = None  # populated if the adapter failed; review still surfaced
    overall: OverallVerdict | None = None

    @property
    def ok(self) -> bool:
        return self.error is None
