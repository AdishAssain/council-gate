"""Learned gate: classify a council's reviews as consensus or disagreement.

Asymmetric by design (see README §"Why the gate is asymmetric"):
- High escalation score → ESCALATE. Reviewers don't agree; humans must adjudicate.
- Low escalation score → CONSENSUS_CHECK. Not auto-approval — surface known
  correlated-failure dimensions for human review.

The verdict is a frozen classifier over features of the structured review
form (seat count, severity mix, dispositions, overall recommendations).
Models ship as JSON in _assets and run in pure Python:
- lr         — logistic regression fit on source-derived labels (default)
- tabpfn-lr  — TabPFN-Lite-LR, distilled from a TabPFN v2 teacher
- tabpfn-gb  — TabPFN-Lite-GB, gradient-boosted trees, same teacher

A block-vs-accept split among reviewers escalates unconditionally: reviewers
can produce near-identical findings yet disagree on whether the artifact is
acceptable.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from enum import StrEnum
from importlib.resources import files
from typing import Any

from council_gate.types import Recommendation, Review, Severity

GATE_MODELS = ("lr", "tabpfn-lr", "tabpfn-gb")

_MODEL_ASSETS = {
    "lr": "gate_lr.json",
    "tabpfn-lr": "gate_tabpfn_lr.json",
    "tabpfn-gb": "gate_tabpfn_gb.json",
}


class Verdict(StrEnum):
    ESCALATE = "escalate"
    CONSENSUS_CHECK = "consensus_check"
    INSUFFICIENT = "insufficient"  # too few reviewers to gate


@dataclass(slots=True, frozen=True)
class GateVerdict:
    verdict: Verdict
    score: float  # escalation probability, 0.0 = consensus, 1.0 = escalate
    reviewer_count: int
    reason: str
    recommendations: tuple[str, ...] = field(default_factory=tuple)


CORRELATED_BLINDSPOT_DIMENSIONS = (
    "novelty",
    "edge cases",
    "failure modes",
    "missing data handling",
    "long-term maintenance",
)

SEVERITY_WEIGHTS: dict[Severity, float] = {
    "critical": 4.0,
    "major": 2.0,
    "minor": 1.0,
    "nit": 0.25,
}

_DISPOSITIONS = ("defect", "risk", "gap", "question", "endorse")
_RECOMMENDATIONS: tuple[Recommendation, ...] = ("block", "revise", "accept")

_FRIENDLY = {
    "n_findings": "total findings",
    "n_ok": "concurring reviewer count",
    "critical_rate": "share of critical findings",
    "major_rate": "share of major findings",
    "mean_sev_w": "mean finding severity",
    "disp_defect": "defect-type findings",
    "disp_risk": "risk-type findings",
    "disp_gap": "gap-type findings",
    "disp_question": "question-type findings",
    "disp_endorse": "endorsements",
    "rec_block": "reviewers recommending block",
    "rec_revise": "reviewers recommending revise",
    "rec_accept": "reviewers recommending accept",
    "polar": "block-vs-accept split",
}


def _features(reviews: list[Review]) -> dict[str, float]:
    ok = [r for r in reviews if r.ok]
    findings = [f for r in ok for f in r.findings]
    recs = [r.overall.recommendation for r in ok if r.overall is not None]
    n = max(len(findings), 1)
    out: dict[str, float] = {
        "n_findings": float(len(findings)),
        "n_ok": float(len(ok)),
        "critical_rate": sum(f.severity == "critical" for f in findings) / n,
        "major_rate": sum(f.severity == "major" for f in findings) / n,
        "mean_sev_w": sum(SEVERITY_WEIGHTS[f.severity] for f in findings) / n,
        "polar": 1.0 if ("block" in recs and "accept" in recs) else 0.0,
    }
    for d in _DISPOSITIONS:
        out[f"disp_{d}"] = sum(f.disposition == d for f in findings) / n
    for rec in _RECOMMENDATIONS:
        out[f"rec_{rec}"] = recs.count(rec) / len(recs) if recs else 0.0
    return out


def _recommendations(reviews: list[Review]) -> tuple[str, ...]:
    return tuple(r.overall.recommendation for r in reviews if r.ok and r.overall)


def _score_linear(x: list[float], m: dict[str, Any]) -> tuple[float, list[float]]:
    """Return (probability, per-feature contribution to the logit)."""
    contribs = [
        w * ((xi - mu) / sd)
        for xi, mu, sd, w in zip(x, m["means"], m["stds"], m["coefs"], strict=True)
    ]
    z = m["intercept"] + sum(contribs)
    return 1.0 / (1.0 + math.exp(-z)), contribs


def _score_gb(x: list[float], m: dict[str, Any]) -> float:
    raw = m["init_raw"]
    for t in m["trees"]:
        node = 0
        while t["cl"][node] != -1:
            node = t["cl"][node] if x[t["feat"][node]] <= t["thr"][node] else t["cr"][node]
        raw += m["learning_rate"] * t["val"][node]
    return 1.0 / (1.0 + math.exp(-raw))


class LearnedGate:
    def __init__(self, model: str = "lr", threshold: float = 0.5) -> None:
        if model not in _MODEL_ASSETS:
            raise ValueError(f"unknown gate model {model!r}; choose from {GATE_MODELS}")
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(f"threshold must be in [0, 1], got {threshold}")
        self.model_name = model
        self.threshold = threshold
        self._m = json.loads(
            files("council_gate._assets").joinpath(_MODEL_ASSETS[model]).read_text()
        )

    def evaluate(self, reviews: list[Review]) -> GateVerdict:
        ok = [r for r in reviews if r.ok]
        recs = _recommendations(reviews)
        if len(ok) < 2:
            return GateVerdict(
                verdict=Verdict.INSUFFICIENT,
                score=0.0,
                reviewer_count=len(ok),
                reason=f"need >=2 successful reviewers, got {len(ok)}",
                recommendations=recs,
            )
        feats = _features(reviews)
        x = [feats[name] for name in self._m["features"]]
        if self._m["type"] == "linear":
            prob, contribs = _score_linear(x, self._m)
            drivers = self._drivers(contribs)
        else:
            prob = _score_gb(x, self._m)
            drivers = f"{len(self._m['trees'])}-tree learned ensemble"

        if "block" in recs and "accept" in recs:
            return GateVerdict(
                verdict=Verdict.ESCALATE,
                score=max(prob, self.threshold),
                reviewer_count=len(ok),
                reason=(
                    f"overall verdicts conflict ({', '.join(recs)}) — one reviewer "
                    "would block what another would accept; human adjudication required."
                ),
                recommendations=recs,
            )
        if prob >= self.threshold:
            return GateVerdict(
                verdict=Verdict.ESCALATE,
                score=prob,
                reviewer_count=len(ok),
                reason=f"escalation score {prob:.2f} >= {self.threshold:.2f} ({drivers})",
                recommendations=recs,
            )
        return GateVerdict(
            verdict=Verdict.CONSENSUS_CHECK,
            score=prob,
            reviewer_count=len(ok),
            reason=(
                f"escalation score {prob:.2f} < {self.threshold:.2f} ({drivers}). "
                "Consensus is not approval — verify against correlated-blindspot "
                "dimensions before trusting."
            ),
            recommendations=recs,
        )

    def _drivers(self, contribs: list[float]) -> str:
        ranked = sorted(
            zip(self._m["features"], contribs, strict=True), key=lambda p: -abs(p[1])
        )
        parts = [
            f"{_FRIENDLY.get(name, name)} {'→escalate' if c > 0 else '→consensus'}"
            for name, c in ranked[:3]
            if abs(c) > 1e-9
        ]
        return "; ".join(parts) if parts else "no strong drivers"
