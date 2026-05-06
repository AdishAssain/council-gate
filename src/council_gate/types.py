from dataclasses import dataclass
from typing import Literal

Severity = Literal["critical", "major", "minor", "nit"]


@dataclass(slots=True, frozen=True)
class Finding:
    severity: Severity
    summary: str
    location: str | None = None


@dataclass(slots=True)
class Review:
    model_id: str
    provider: str
    findings: list[Finding]
    raw_text: str = ""
    error: str | None = None  # populated if the adapter failed; review still surfaced

    @property
    def ok(self) -> bool:
        return self.error is None
