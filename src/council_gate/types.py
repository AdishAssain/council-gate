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


@dataclass(slots=True, frozen=True)
class Finding:
    severity: Severity
    summary: str
    location: str | None = None
    category: Category = "unspecified"
    rationale: str = ""
    evidence_quote: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "summary": self.summary,
            "location": self.location,
            "category": self.category,
            "rationale": self.rationale,
            "evidence_quote": self.evidence_quote,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Finding":
        sev = d.get("severity", "minor")
        if sev not in _VALID_SEVERITIES:
            sev = "minor"
        cat = d.get("category", "unspecified")
        if cat not in _VALID_CATEGORIES:
            cat = "unspecified"
        return cls(
            severity=sev,  # type: ignore[arg-type]
            summary=str(d.get("summary", "")).strip(),
            location=d.get("location") or None,
            category=cat,  # type: ignore[arg-type]
            rationale=str(d.get("rationale", "")).strip(),
            evidence_quote=d.get("evidence_quote") or None,
        )


@dataclass(slots=True)
class Review:
    model_id: str
    provider: str
    findings: list[Finding] = field(default_factory=list)
    raw_text: str = ""
    error: str | None = None  # populated if the adapter failed; review still surfaced

    @property
    def ok(self) -> bool:
        return self.error is None
