from council_gate.clustering import FindingCluster, cluster_findings
from council_gate.embeddings import HashEmbedder
from council_gate.types import Finding


def _f(severity, summary, category="correctness", rationale=""):
    return Finding(
        severity=severity, summary=summary, category=category, rationale=rationale
    )


def test_empty_input():
    assert cluster_findings([], HashEmbedder()) == []


def test_single_finding_one_cluster():
    labeled = [("openai", _f("major", "null deref expired session"))]
    clusters = cluster_findings(labeled, HashEmbedder())
    assert len(clusters) == 1
    assert clusters[0].n_reviewers == 1


def test_identical_findings_merge():
    text = "null check missing in parser line forty two"
    labeled = [
        ("openai", _f("major", text)),
        ("anthropic", _f("major", text)),
    ]
    clusters = cluster_findings(labeled, HashEmbedder())
    assert len(clusters) == 1
    assert clusters[0].n_reviewers == 2
    assert set(clusters[0].contributing_reviewers) == {"openai", "anthropic"}


def test_disjoint_findings_stay_apart():
    labeled = [
        ("openai", _f("critical", "security flaw authentication token validation")),
        ("anthropic", _f("major", "performance regression render loop animation timer")),
    ]
    clusters = cluster_findings(labeled, HashEmbedder())
    assert len(clusters) == 2


def test_max_severity_propagates():
    text = "null pointer crash on shutdown"
    labeled = [
        ("a", _f("minor", text)),
        ("b", _f("critical", text)),
        ("c", _f("major", text)),
    ]
    clusters = cluster_findings(labeled, HashEmbedder())
    assert len(clusters) == 1
    assert clusters[0].max_severity == "critical"


def test_category_mode_wins():
    text = "shared issue summary across reviewers same text"
    labeled = [
        ("a", _f("minor", text, category="performance")),
        ("b", _f("minor", text, category="performance")),
        ("c", _f("minor", text, category="correctness")),
    ]
    clusters = cluster_findings(labeled, HashEmbedder())
    assert len(clusters) == 1
    assert clusters[0].category == "performance"


def test_cluster_summary_is_highest_severity_member():
    labeled = [
        ("a", _f("minor", "minor variant summary same shared tokens")),
        ("b", _f("critical", "critical variant summary same shared tokens")),
    ]
    clusters = cluster_findings(labeled, HashEmbedder())
    assert len(clusters) == 1
    assert clusters[0].summary.startswith("critical")


def test_cluster_is_frozen_dataclass():
    c = FindingCluster(
        category="correctness",
        max_severity="major",
        summary="x",
        contributing_reviewers=("a", "b"),
    )
    assert c.n_reviewers == 2
