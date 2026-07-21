"""Entropy gate: classify a council's reviews as consensus or disagreement.

Asymmetric by design (see README §"Why the gate is asymmetric"):
- High disagreement → ESCALATE. Reviewers don't agree; humans must adjudicate.
- Low disagreement → CONSENSUS_CHECK. Not auto-approval — surface known
  correlated-failure dimensions for human review.

Two scoring backends:
- EntropyGate (v1): mean (1 - Jaccard) over reviewer pairs, token-bag based.
  Crude, vocabulary-sensitive, nits weighted equally with criticals.
- EntropyGateV2: severity-weighted semantic agreement over finding clusters.
  Requires an Embedder (see council_gate.embeddings).
"""
from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from enum import StrEnum

from council_gate.clustering import FindingCluster, cluster_findings
from council_gate.embeddings import Embedder
from council_gate.types import Review, Severity

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
    pair_distances: tuple[tuple[str, str, float], ...] = field(default_factory=tuple)
    clusters: tuple[FindingCluster, ...] = field(default_factory=tuple)
    severity_weighted: bool = False
    # Top-cluster signal: of the critical/major clusters, what's the largest
    # fraction of reviewers that converged on a single serious issue? This is
    # the "did the council unanimously catch a real bug" metric — the entropy
    # score is dominated by singleton noise, so this auxiliary lets downstream
    # consumers see consensus when it exists.
    top_cluster_agreement: float = 0.0
    top_cluster_severity: Severity | None = None
    top_cluster_summary: str | None = None


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


def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{4,}", s.lower())}


def _pairwise_disagreement(
    reviews: list[Review],
) -> tuple[float, int, tuple[tuple[str, str, float], ...]]:
    """Mean (1 - Jaccard) over reviewer pairs that have non-empty token bags.

    Returns (mean_disagreement, comparable_pair_count, per_pair_distances).
    Pairs where both reviewers' token bags are empty are skipped — treating
    them as agreement is a false-consensus bug.
    """
    bags: list[tuple[str, set[str]]] = []
    for r in reviews:
        toks: set[str] = set()
        for f in r.findings:
            toks |= _tokens(f.summary)
        if not toks and r.raw_text:
            toks = _tokens(r.raw_text)
        bags.append((r.model_id, toks))

    distances: list[float] = []
    pair_records: list[tuple[str, str, float]] = []
    for i in range(len(bags)):
        for j in range(i + 1, len(bags)):
            id_a, a = bags[i]
            id_b, b = bags[j]
            if not a and not b:
                continue  # both empty: not comparable, skip
            jaccard = len(a & b) / max(len(a | b), 1)
            d = 1.0 - jaccard
            distances.append(d)
            pair_records.append((id_a, id_b, d))
    if not distances:
        return 0.0, 0, ()
    mean = sum(distances) / len(distances)
    return mean, len(distances), tuple(pair_records)


_MAX_SEVERITY_WEIGHT = max(SEVERITY_WEIGHTS.values())

_SERIOUS_SEVERITIES: frozenset[Severity] = frozenset(("critical", "major"))

# Critical singletons survive truncation — one reviewer catching a real
# critical is still signal.
_KEEP_SINGLETON_SEVERITIES: frozenset[Severity] = frozenset(("critical",))


def _top_cluster_agreement(
    clusters: list[FindingCluster], n_reviewers: int
) -> tuple[float, Severity | None, str | None]:
    """Find the largest critical/major cluster and return its agreement fraction.

    The entropy score is dominated by singleton-finding noise. This signal
    bypasses that by asking: ignoring nits and minors, what's the most-agreed
    serious finding? Tie-break by severity (critical > major).
    """
    if n_reviewers <= 0:
        return 0.0, None, None
    serious = [c for c in clusters if c.max_severity in _SERIOUS_SEVERITIES]
    if not serious:
        return 0.0, None, None
    best = max(
        serious,
        key=lambda c: (c.n_reviewers, SEVERITY_WEIGHTS.get(c.max_severity, 0.0)),
    )
    return best.n_reviewers / n_reviewers, best.max_severity, best.summary


def _severity_weighted_entropy(
    clusters: list[FindingCluster], n_reviewers: int
) -> float:
    """Severity-weighted Shannon entropy × severity density, normalized to [0, 1].

    Two-factor disagreement:
    1. Entropy term: how spread-out the findings are across clusters.
       Weight cluster i by w_i = n_reviewers_in_cluster × severity_weight(s_i).
       Treat as probability distribution, compute Shannon entropy, normalize
       by log(K) so result is in [0, 1].
    2. Severity-density term: mean cluster severity / max severity weight.
       Dampens disagreement when reviewers diverge only on nits.

    disagreement = H_normalized × severity_density.

    Returns 0.0 when there's only one cluster (perfect agreement) or no
    findings parsed.
    """
    K = len(clusters)
    if K < 2 or n_reviewers <= 0:
        return 0.0
    weights = [
        c.n_reviewers * SEVERITY_WEIGHTS.get(c.max_severity, 1.0) for c in clusters
    ]
    total = sum(weights)
    if total <= 0:
        return 0.0
    h = 0.0
    for w in weights:
        if w > 0:
            p = w / total
            h -= p * math.log(p)
    h_max = math.log(K)
    h_norm = h / h_max if h_max > 0 else 0.0
    severity_mean = (
        sum(SEVERITY_WEIGHTS.get(c.max_severity, 1.0) for c in clusters) / K
    )
    severity_density = severity_mean / _MAX_SEVERITY_WEIGHT
    return h_norm * severity_density


class EntropyGate:
    """V1: token-bag Jaccard, no semantic awareness, severity-blind."""

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

        d, pair_count, pair_records = _pairwise_disagreement(ok_reviews)
        log.info(
            "gate-v1: disagreement=%.3f threshold=%.3f comparable_pairs=%d",
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
                pair_distances=pair_records,
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
            pair_distances=pair_records,
        )


class EntropyGateV2:
    """V2: severity-weighted Shannon entropy over semantic finding clusters.

    Two reviewers describing the same flaw with different wording cluster
    together. Disagreement = normalized Shannon entropy of the cluster
    severity-weighted distribution × severity density. Both terms in [0, 1].

    Two extra controls override raw entropy where it misfires:

    1. Singleton truncation (SVD-style noise floor): clusters with fewer
       than `min_cluster_size` reviewers contribute as "noise" and aren't
       counted in the entropy sum. Default 2 — singletons drop out.
    2. Top-cluster consensus override: if any critical/major cluster has
       `top_cluster_agreement >= consensus_override_min`, the verdict is
       forced to CONSENSUS_CHECK regardless of entropy. Strong unanimous
       agreement on a serious finding *is* consensus, even when each
       reviewer also raises their own singleton tail.
    """

    def __init__(
        self,
        embedder: Embedder,
        threshold: float = 0.30,
        cluster_threshold: float = 0.65,
        min_cluster_size: int = 2,
        consensus_override_min: float = 0.80,
    ) -> None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(f"threshold must be in [0, 1], got {threshold}")
        if not 0.0 <= cluster_threshold <= 1.0:
            raise ValueError(
                f"cluster_threshold must be in [0, 1], got {cluster_threshold}"
            )
        if min_cluster_size < 1:
            raise ValueError(
                f"min_cluster_size must be >= 1, got {min_cluster_size}"
            )
        # Values > 1.0 effectively disable the override (top_cluster_agreement
        # is always <= 1.0). Useful for ablation studies.
        if consensus_override_min < 0.0:
            raise ValueError(
                f"consensus_override_min must be >= 0, got {consensus_override_min}"
            )
        self.embedder = embedder
        self.threshold = threshold
        self.cluster_threshold = cluster_threshold
        self.min_cluster_size = min_cluster_size
        self.consensus_override_min = consensus_override_min

    def evaluate(self, reviews: list[Review]) -> GateVerdict:
        ok_reviews = [r for r in reviews if r.ok]
        if len(ok_reviews) < 2:
            return GateVerdict(
                verdict=Verdict.INSUFFICIENT,
                disagreement=0.0,
                reviewer_count=len(ok_reviews),
                reason=f"need >=2 successful reviewers, got {len(ok_reviews)}",
                severity_weighted=True,
            )

        labeled = [(r.model_id, f) for r in ok_reviews for f in r.findings]
        if not labeled:
            return GateVerdict(
                verdict=Verdict.INSUFFICIENT,
                disagreement=0.0,
                reviewer_count=len(ok_reviews),
                reason=(
                    "no parsed findings across reviewers — JSON parsing likely "
                    "failed; check raw_text and consider lowering threshold"
                ),
                severity_weighted=True,
            )

        clusters = cluster_findings(
            labeled, self.embedder, threshold=self.cluster_threshold
        )
        signal_clusters = [
            c
            for c in clusters
            if c.n_reviewers >= self.min_cluster_size
            or c.max_severity in _KEEP_SINGLETON_SEVERITIES
        ]
        # Fall back to all clusters when truncation would empty the set,
        # otherwise we'd fake-zero the disagreement.
        entropy_clusters = signal_clusters if signal_clusters else clusters
        disagreement = _severity_weighted_entropy(entropy_clusters, len(ok_reviews))
        top_frac, top_sev, top_summary = _top_cluster_agreement(
            clusters, len(ok_reviews)
        )
        log.info(
            "gate-v2: disagreement=%.3f threshold=%.3f clusters=%d "
            "signal_clusters=%d (used_for_entropy=%d) reviewers=%d "
            "top_cluster_agreement=%.2f (severity=%s)",
            disagreement,
            self.threshold,
            len(clusters),
            len(signal_clusters),
            len(entropy_clusters),
            len(ok_reviews),
            top_frac,
            top_sev,
        )

        # Override entropy when reviewers strongly agree on a serious finding.
        # Without this, a singleton tail inflates entropy past threshold even
        # when the load-bearing finding is unanimous.
        if (
            top_frac >= self.consensus_override_min
            and top_sev in ("critical", "major")
        ):
            return GateVerdict(
                verdict=Verdict.CONSENSUS_CHECK,
                disagreement=disagreement,
                reviewer_count=len(ok_reviews),
                reason=(
                    f"top_cluster_agreement {top_frac:.2f} >= "
                    f"{self.consensus_override_min:.2f} on a {top_sev} finding "
                    "— strong consensus on a serious issue overrides entropy."
                ),
                clusters=tuple(clusters),
                severity_weighted=True,
                top_cluster_agreement=top_frac,
                top_cluster_severity=top_sev,
                top_cluster_summary=top_summary,
            )

        if disagreement >= self.threshold:
            return GateVerdict(
                verdict=Verdict.ESCALATE,
                disagreement=disagreement,
                reviewer_count=len(ok_reviews),
                reason=(
                    f"weighted disagreement {disagreement:.2f} "
                    f">= threshold {self.threshold:.2f} across "
                    f"{len(signal_clusters)} signal clusters "
                    f"(of {len(clusters)} total; singletons truncated)"
                ),
                clusters=tuple(clusters),
                severity_weighted=True,
                top_cluster_agreement=top_frac,
                top_cluster_severity=top_sev,
                top_cluster_summary=top_summary,
            )
        return GateVerdict(
            verdict=Verdict.CONSENSUS_CHECK,
            disagreement=disagreement,
            reviewer_count=len(ok_reviews),
            reason=(
                f"weighted disagreement {disagreement:.2f} "
                f"< threshold {self.threshold:.2f}. Consensus is not approval "
                "— verify against correlated-blindspot dimensions before trusting."
            ),
            clusters=tuple(clusters),
            severity_weighted=True,
            top_cluster_agreement=top_frac,
            top_cluster_severity=top_sev,
            top_cluster_summary=top_summary,
        )
