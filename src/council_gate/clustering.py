"""Cluster semantically similar findings across reviewers.

Cluster = "this issue, raised by these reviewers." Used by the entropy gate
v2 to compute severity-weighted agreement instead of flat Jaccard, so two
reviewers describing the same problem with different vocabulary aren't
mistakenly counted as disagreement.

Algorithm: one-pass agglomerative on cosine similarity. O(N^2) but N is
small (~10-30 findings total across a council).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from council_gate.embeddings import Embedder
from council_gate.types import Category, Finding, Severity

_SEVERITY_RANK: dict[Severity, int] = {"critical": 4, "major": 3, "minor": 2, "nit": 1}


@dataclass(slots=True, frozen=True)
class FindingCluster:
    category: Category
    max_severity: Severity
    summary: str
    contributing_reviewers: tuple[str, ...]

    @property
    def n_reviewers(self) -> int:
        return len(set(self.contributing_reviewers))


def cluster_findings(
    labeled: list[tuple[str, Finding]],
    embedder: Embedder,
    threshold: float = 0.65,
) -> list[FindingCluster]:
    """Group findings by semantic similarity.

    `labeled` is [(reviewer_id, finding), ...]. Returns clusters in the order
    they were created. Each cluster's `summary` is the highest-severity
    member's summary; `category` is the most common category among members
    (ties broken by highest severity); `contributing_reviewers` preserves
    insertion order with duplicates allowed (a reviewer raising the same
    issue twice counts once via n_reviewers).
    """
    if not labeled:
        return []

    texts = [_text_for_embedding(f) for _, f in labeled]
    vectors = embedder.embed(texts)

    # cluster_assignments[i] = index of cluster that finding i belongs to.
    # cluster_centroids[j] = list of vector indices in cluster j.
    cluster_centroids: list[list[int]] = []
    assignments: list[int] = []
    for i, vec in enumerate(vectors):
        best_cluster = -1
        best_sim = threshold
        for cj, members in enumerate(cluster_centroids):
            sim = _max_sim_to_cluster(vec, [vectors[m] for m in members])
            if sim >= best_sim:
                best_sim = sim
                best_cluster = cj
        if best_cluster < 0:
            cluster_centroids.append([i])
            assignments.append(len(cluster_centroids) - 1)
        else:
            cluster_centroids[best_cluster].append(i)
            assignments.append(best_cluster)

    return [
        _build_cluster([labeled[i] for i in members])
        for members in cluster_centroids
    ]


def _text_for_embedding(f: Finding) -> str:
    """Combine summary + rationale; richer signal than summary alone."""
    if f.rationale:
        return f"{f.summary}. {f.rationale}"
    return f.summary


def _max_sim_to_cluster(vec: list[float], members: list[list[float]]) -> float:
    return max(_cosine(vec, m) for m in members)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _build_cluster(members: list[tuple[str, Finding]]) -> FindingCluster:
    top_finding = max(members, key=lambda rf: _SEVERITY_RANK.get(rf[1].severity, 0))[1]
    category_counts = Counter(f.category for _, f in members)
    top_count = max(category_counts.values())
    tied = [c for c, n in category_counts.items() if n == top_count]
    if len(tied) == 1:
        category = tied[0]
    else:
        category = top_finding.category  # break tie by highest-severity member
    return FindingCluster(
        category=category,
        max_severity=top_finding.severity,
        summary=top_finding.summary,
        contributing_reviewers=tuple(r for r, _ in members),
    )
