from dataclasses import dataclass, field
from typing import Any, Literal, cast

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


def _enum_or(
    d: dict[str, Any], key: str, allowed: frozenset[str], default: str | None
) -> str | None:
    # isinstance first: `x in frozenset` raises TypeError on unhashable input.
    v = d.get(key, default)
    if not isinstance(v, str):
        return default
    v = v.strip().lower()
    return v if v in allowed else default


def _str_or_none(d: dict[str, Any], key: str) -> str | None:
    v = d.get(key)
    return v if isinstance(v, str) and v else None


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
        return cls(
            severity=cast(Severity, _enum_or(d, "severity", _VALID_SEVERITIES, "minor")),
            summary=str(d.get("summary", "")).strip(),
            location=_str_or_none(d, "location"),
            category=cast(
                Category, _enum_or(d, "category", _VALID_CATEGORIES, "unspecified")
            ),
            rationale=str(d.get("rationale", "")).strip(),
            evidence_quote=_str_or_none(d, "evidence_quote"),
            disposition=cast(
                Disposition, _enum_or(d, "disposition", _VALID_DISPOSITIONS, "defect")
            ),
            confidence=cast(
                "Confidence | None", _enum_or(d, "confidence", _VALID_CONFIDENCES, None)
            ),
        )


@dataclass(slots=True, frozen=True)
class OverallVerdict:
    """A reviewer's artifact-level stance, distinct from its findings."""

    recommendation: Recommendation
    severity: Severity
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommendation": self.recommendation,
            "severity": self.severity,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "OverallVerdict":
        return cls(
            recommendation=cast(
                Recommendation,
                _enum_or(d, "recommendation", _VALID_RECOMMENDATIONS, "revise"),
            ),
            severity=cast(Severity, _enum_or(d, "severity", _VALID_SEVERITIES, "minor")),
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
