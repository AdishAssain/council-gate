"""Entropy gate: read a council's reviews, classify consensus vs disagreement.

The gate is asymmetric by design (see README §"Why the gate is asymmetric"):
- High disagreement → ESCALATE. Reviewers don't agree; humans must adjudicate.
- Low disagreement → CONSENSUS_CHECK. Don't auto-trust — surface known
  correlated-failure dimensions for human review.

The disagreement metric in v0 is a simple set-distance over normalized finding
summaries. This is intentionally crude. Upgrade path: embed findings, cluster,
compute Jaccard over clusters.
"""
import logging
import re
from dataclasses import dataclass
from enum import StrEnum

from council_gate.types import Review

log = logging.getLogger(__name__)


class Verdict(StrEnum):
    ESCALATE = "escalate"
    CONSENSUS_CHECK = "consensus_check"
    INSUFFICIENT = "insufficient"  # too few reviewers to gate


@dataclass(slots=True, frozen=True)
class GateVerdict:
    verdict: Verdict
    disagreement: float  # 0.0 = identical, 1.0 = no overlap
    reviewer_count: int
    reason: str


CORRELATED_BLINDSPOT_DIMENSIONS = (
    "novelty",
    "edge cases",
    "failure modes",
    "missing data handling",
    "long-term maintenance",
)


def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{4,}", s.lower())}


def _pairwise_disagreement(reviews: list[Review]) -> tuple[float, int]:
    """Mean (1 - Jaccard) over reviewer pairs that have non-empty token bags.

    Returns (mean_disagreement, comparable_pair_count). If a reviewer's
    findings parse to nothing, falls back to its raw_text — but pairs where
    BOTH sides are empty are excluded entirely (treating them as agreement
    is a false-consensus bug; see independent review notes).
    """
    bags: list[set[str]] = []
    for r in reviews:
        toks: set[str] = set()
        for f in r.findings:
            toks |= _tokens(f.summary)
        if not toks and r.raw_text:
            toks = _tokens(r.raw_text)
        bags.append(toks)

    distances: list[float] = []
    for i in range(len(bags)):
        for j in range(i + 1, len(bags)):
            a, b = bags[i], bags[j]
            if not a and not b:
                continue  # both empty: not comparable, skip
            jaccard = len(a & b) / max(len(a | b), 1)
            distances.append(1.0 - jaccard)
    if not distances:
        return 0.0, 0
    return sum(distances) / len(distances), len(distances)


class EntropyGate:
    def __init__(self, threshold: float = 0.35) -> None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(f"threshold must be in [0, 1], got {threshold}")
        self.threshold = threshold

    def evaluate(self, reviews: list[Review]) -> GateVerdict:
        ok_reviews = [r for r in reviews if r.ok]
        if len(ok_reviews) < 2:
            return GateVerdict(
                verdict=Verdict.INSUFFICIENT,
                disagreement=0.0,
                reviewer_count=len(ok_reviews),
                reason=f"need >=2 successful reviewers, got {len(ok_reviews)}",
            )

        d, pair_count = _pairwise_disagreement(ok_reviews)
        log.info(
            "gate: disagreement=%.3f threshold=%.3f comparable_pairs=%d",
            d,
            self.threshold,
            pair_count,
        )
        if pair_count == 0:
            return GateVerdict(
                verdict=Verdict.INSUFFICIENT,
                disagreement=0.0,
                reviewer_count=len(ok_reviews),
                reason=(
                    "no comparable reviewer pairs (all reviews parsed to empty "
                    "findings AND empty raw_text — likely a parser or adapter bug)"
                ),
            )

        if d >= self.threshold:
            return GateVerdict(
                verdict=Verdict.ESCALATE,
                disagreement=d,
                reviewer_count=len(ok_reviews),
                reason=f"disagreement {d:.2f} >= threshold {self.threshold:.2f}",
            )
        return GateVerdict(
            verdict=Verdict.CONSENSUS_CHECK,
            disagreement=d,
            reviewer_count=len(ok_reviews),
            reason=(
                f"disagreement {d:.2f} < threshold {self.threshold:.2f}. "
                "Consensus is not approval — verify against correlated-blindspot "
                "dimensions before trusting."
            ),
        )
