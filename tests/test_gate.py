import pytest

from council_gate.embeddings import HashEmbedder
from council_gate.gate import EntropyGate, EntropyGateV2, Verdict
from council_gate.types import Finding, OverallVerdict, Review


def _review(provider: str, summaries: list[str]) -> Review:
    return Review(
        model_id=f"{provider}/test",
        provider=provider,
        findings=[Finding(severity="major", summary=s) for s in summaries],
        raw_text=" ".join(summaries),
    )


def _review_with(provider: str, findings: list[Finding]) -> Review:
    return Review(
        model_id=f"{provider}/test",
        provider=provider,
        findings=findings,
        raw_text=" ".join(f.summary for f in findings),
    )


def test_insufficient_when_one_reviewer():
    gate = EntropyGate(threshold=0.35)
    v = gate.evaluate([_review("openai", ["foo bar baz qux"])])
    assert v.verdict == Verdict.INSUFFICIENT
    assert v.reviewer_count == 1


def test_consensus_when_reviews_overlap():
    gate = EntropyGate(threshold=0.35)
    a = _review("openai", ["null check missing in parser line forty two"])
    b = _review("anthropic", ["null check missing in parser line forty two"])
    v = gate.evaluate([a, b])
    assert v.verdict == Verdict.CONSENSUS_CHECK
    assert v.disagreement < 0.35


def test_escalate_when_reviews_disagree():
    gate = EntropyGate(threshold=0.35)
    a = _review("openai", ["security flaw authentication module token validation"])
    b = _review("anthropic", ["performance regression render loop animation timer"])
    v = gate.evaluate([a, b])
    assert v.verdict == Verdict.ESCALATE
    assert v.disagreement >= 0.35


def test_failed_reviews_excluded_from_count():
    gate = EntropyGate(threshold=0.35)
    a = _review("openai", ["x y z"])
    bad = Review(
        model_id="anthropic/x", provider="anthropic", findings=[], error="timeout"
    )
    v = gate.evaluate([a, bad])
    assert v.verdict == Verdict.INSUFFICIENT


def test_threshold_validated():
    with pytest.raises(ValueError):
        EntropyGate(threshold=1.5)
    with pytest.raises(ValueError):
        EntropyGate(threshold=-0.1)


def test_all_empty_reviews_returns_insufficient_not_consensus():
    """Independent review caught this: two reviewers with empty findings AND
    empty raw_text would previously score 0.0 disagreement and trigger
    CONSENSUS_CHECK — i.e. fake agreement on parser failure."""
    gate = EntropyGate(threshold=0.35)
    a = Review(model_id="openai/x", provider="openai", findings=[], raw_text="")
    b = Review(model_id="anthropic/x", provider="anthropic", findings=[], raw_text="")
    v = gate.evaluate([a, b])
    assert v.verdict == Verdict.INSUFFICIENT
    assert "no comparable" in v.reason


def test_v1_persists_pair_distances():
    gate = EntropyGate(threshold=0.35)
    a = _review("openai", ["security flaw authentication module"])
    b = _review("anthropic", ["performance regression render loop"])
    v = gate.evaluate([a, b])
    assert len(v.pair_distances) == 1
    src_a, src_b, dist = v.pair_distances[0]
    assert "openai" in src_a or "anthropic" in src_a
    assert 0.0 <= dist <= 1.0


# ---------- EntropyGateV2 (severity-weighted semantic) ----------


def _f(sev, summary, category="correctness"):
    return Finding(severity=sev, summary=summary, category=category)


def test_v2_insufficient_with_one_reviewer():
    gate = EntropyGateV2(embedder=HashEmbedder())
    a = _review_with("openai", [_f("major", "x")])
    v = gate.evaluate([a])
    assert v.verdict == Verdict.INSUFFICIENT
    assert v.severity_weighted is True


def test_v2_full_consensus_on_critical():
    gate = EntropyGateV2(embedder=HashEmbedder(), threshold=0.40)
    shared = "null deref expired session shared text tokens"
    a = _review_with("openai", [_f("critical", shared)])
    b = _review_with("anthropic", [_f("critical", shared)])
    c = _review_with("google", [_f("critical", shared)])
    v = gate.evaluate([a, b, c])
    assert v.verdict == Verdict.CONSENSUS_CHECK
    assert v.disagreement < 0.05
    assert len(v.clusters) == 1
    assert v.clusters[0].max_severity == "critical"


def test_v2_high_disagreement_on_disjoint_criticals():
    gate = EntropyGateV2(embedder=HashEmbedder(), threshold=0.40)
    a = _review_with("openai", [_f("critical", "security flaw authentication tokens")])
    b = _review_with("anthropic", [_f("critical", "performance regression render loop")])
    c = _review_with("google", [_f("critical", "data corruption migration schema")])
    v = gate.evaluate([a, b, c])
    assert v.verdict == Verdict.ESCALATE
    assert v.disagreement > 0.5
    assert len(v.clusters) == 3


def test_v2_nits_dont_dominate_critical_consensus():
    """All reviewers agree on a critical, but each adds their own nit.
    Severity-weighted agreement should still classify as consensus."""
    gate = EntropyGateV2(embedder=HashEmbedder(), threshold=0.40)
    shared = "buffer overflow boundary check missing same shared tokens"
    a = _review_with(
        "openai",
        [_f("critical", shared), _f("nit", "openai unique trailing whitespace nit")],
    )
    b = _review_with(
        "anthropic",
        [_f("critical", shared), _f("nit", "anthropic unique naming style nit")],
    )
    c = _review_with(
        "google",
        [_f("critical", shared), _f("nit", "google unique import ordering nit")],
    )
    v = gate.evaluate([a, b, c])
    # Critical cluster dominates the severity-weighted distribution (weight
    # 12) vs 3 tiny nit clusters (0.25 each). Entropy is low (one bin near
    # 1), and severity_density is dragged down by the nits. Net disagreement
    # well under threshold.
    assert v.verdict == Verdict.CONSENSUS_CHECK
    assert v.disagreement < 0.20


def test_v2_no_findings_returns_insufficient():
    gate = EntropyGateV2(embedder=HashEmbedder())
    a = Review(
        model_id="openai/x", provider="openai", findings=[], raw_text="some prose"
    )
    b = Review(
        model_id="anthropic/x",
        provider="anthropic",
        findings=[],
        raw_text="other prose",
    )
    v = gate.evaluate([a, b])
    assert v.verdict == Verdict.INSUFFICIENT
    assert "no parsed findings" in v.reason


def test_v2_threshold_validated():
    with pytest.raises(ValueError):
        EntropyGateV2(embedder=HashEmbedder(), threshold=1.5)
    with pytest.raises(ValueError):
        EntropyGateV2(embedder=HashEmbedder(), cluster_threshold=-0.1)


def test_v2_top_cluster_agreement_unanimous_critical():
    """Six reviewers all flag the same SQL injection. top_cluster_agreement
    should be 1.0 and severity 'critical', regardless of nit noise around it."""
    gate = EntropyGateV2(embedder=HashEmbedder())
    shared = "sql injection unparameterized user input concatenation"
    reviewers = [
        _review_with(name, [_f("critical", shared, "security")])
        for name in ("a", "b", "c", "d", "e", "f")
    ]
    v = gate.evaluate(reviewers)
    assert v.top_cluster_agreement == 1.0
    assert v.top_cluster_severity == "critical"
    assert v.top_cluster_summary is not None
    assert "sql" in v.top_cluster_summary.lower()


def test_v2_top_cluster_agreement_partial_with_nit_noise():
    """The headline finding I wanted: 5-of-6 agree on a critical, plus each
    has their own nit. Entropy score may be middling, but top_cluster_agreement
    surfaces the strong consensus cleanly."""
    gate = EntropyGateV2(embedder=HashEmbedder())
    shared_crit = "buffer overflow boundary check missing critical issue"
    reviewers = []
    for name in ("a", "b", "c", "d", "e"):
        reviewers.append(
            _review_with(
                name,
                [
                    _f("critical", shared_crit, "security"),
                    _f("nit", f"{name} unique nit different tokens entirely"),
                ],
            )
        )
    reviewers.append(
        _review_with("dissent", [_f("nit", "dissent unique nit totally different")])
    )
    v = gate.evaluate(reviewers)
    assert v.top_cluster_agreement == 5 / 6
    assert v.top_cluster_severity == "critical"


def test_v2_top_cluster_agreement_zero_when_only_nits():
    """No critical/major clusters exist → top_cluster_agreement = 0 with
    severity None. The signal stays silent rather than misleading on nit unity."""
    gate = EntropyGateV2(embedder=HashEmbedder())
    shared_nit = "trailing whitespace cosmetic style preference"
    reviewers = [
        _review_with(name, [_f("nit", shared_nit)])
        for name in ("a", "b", "c")
    ]
    v = gate.evaluate(reviewers)
    assert v.top_cluster_agreement == 0.0
    assert v.top_cluster_severity is None
    assert v.top_cluster_summary is None


def test_v2_top_cluster_agreement_prefers_critical_on_tie():
    """When two clusters have the same n_reviewers, the critical one wins."""
    gate = EntropyGateV2(embedder=HashEmbedder())
    crit_text = "security flaw critical authentication bypass"
    major_text = "performance regression major render loop"
    reviewers = [
        _review_with(
            "a",
            [_f("critical", crit_text, "security"), _f("major", major_text, "performance")],
        ),
        _review_with(
            "b",
            [_f("critical", crit_text, "security"), _f("major", major_text, "performance")],
        ),
    ]
    v = gate.evaluate(reviewers)
    assert v.top_cluster_agreement == 1.0
    assert v.top_cluster_severity == "critical"


def test_v1_top_cluster_agreement_defaults_to_zero():
    """V1 doesn't cluster — top_cluster_agreement stays at the default 0.0."""
    gate = EntropyGate(threshold=0.35)
    a = _review("openai", ["finding one"])
    b = _review("anthropic", ["finding two"])
    v = gate.evaluate([a, b])
    assert v.top_cluster_agreement == 0.0
    assert v.top_cluster_severity is None
    assert v.top_cluster_summary is None


def test_v2_consensus_override_fires_on_unanimous_critical_with_nit_tail():
    """The motivating bug: 6 reviewers all flag the same critical, plus each
    has their own singleton nit. Entropy hits ~0.35 from the singleton tail;
    without the override the gate would ESCALATE. With override, the
    unanimous critical wins and the verdict is CONSENSUS_CHECK."""
    gate = EntropyGateV2(
        embedder=HashEmbedder(), threshold=0.30, consensus_override_min=0.80
    )
    shared = "buffer overflow boundary check missing critical issue here"
    reviewers = []
    for name in ("a", "b", "c", "d", "e", "f"):
        reviewers.append(
            _review_with(
                name,
                [
                    _f("critical", shared, "security"),
                    _f("nit", f"{name} unique singleton totally different tokens"),
                ],
            )
        )
    v = gate.evaluate(reviewers)
    assert v.verdict == Verdict.CONSENSUS_CHECK
    assert v.top_cluster_agreement == 1.0
    assert "overrides entropy" in v.reason


def test_v2_consensus_override_does_not_fire_on_minor_or_nit():
    """Override is for serious findings only. Unanimous nit agreement doesn't
    suppress entropy-based disagreement on the criticals."""
    gate = EntropyGateV2(
        embedder=HashEmbedder(), threshold=0.30, consensus_override_min=0.80
    )
    shared_nit = "trailing whitespace cosmetic stylistic preference"
    # Each reviewer's critical uses a disjoint vocabulary so HashEmbedder
    # won't accidentally cluster them.
    unique_crit = {
        "a": "alpha bravo charlie delta",
        "b": "foxtrot golf hotel india",
        "c": "kilo lima mike november",
    }
    reviewers = [
        _review_with(
            name,
            [_f("nit", shared_nit), _f("critical", unique_crit[name])],
        )
        for name in ("a", "b", "c")
    ]
    v = gate.evaluate(reviewers)
    assert v.verdict == Verdict.ESCALATE
    assert v.top_cluster_severity == "critical"
    assert v.top_cluster_agreement < 1.0


def test_v2_consensus_override_threshold_tunable():
    """Setting consensus_override_min to 1.0 only fires the override on
    perfectly unanimous critical, not 5/6."""
    strict = EntropyGateV2(
        embedder=HashEmbedder(), threshold=0.30, consensus_override_min=1.0
    )
    shared = "critical issue shared by most reviewers here we go"
    reviewers = [
        _review_with(
            name,
            [
                _f("critical", shared, "security"),
                _f("nit", f"{name} unique nit tokens differ greatly"),
            ],
        )
        for name in ("a", "b", "c", "d", "e")
    ]
    # 6th reviewer disagrees on the critical
    reviewers.append(
        _review_with("f", [_f("critical", "completely different critical issue tokens")])
    )
    v = strict.evaluate(reviewers)
    # 5/6 agreement falls below the strict 1.0 override
    assert v.top_cluster_agreement < 1.0
    assert v.verdict == Verdict.ESCALATE


def test_v2_singleton_truncation_drops_non_critical_noise():
    """When there's at least one shared cluster, non-critical singletons
    are noise and get truncated from entropy. Verifies that disagreement
    drops compared to the no-truncation baseline."""
    truncating = EntropyGateV2(
        embedder=HashEmbedder(),
        threshold=0.30,
        min_cluster_size=2,
        consensus_override_min=2.0,  # > 1.0 disables override
    )
    no_trunc = EntropyGateV2(
        embedder=HashEmbedder(),
        threshold=0.30,
        min_cluster_size=1,
        consensus_override_min=2.0,
    )
    shared = "shared major issue identifiable problem area"
    # Disjoint vocabularies per reviewer for the singleton minor findings.
    unique_minor = {
        "a": "alpha bravo charlie delta",
        "b": "foxtrot golf hotel india",
        "c": "kilo lima mike november",
    }
    reviewers = [
        _review_with(
            name,
            [_f("major", shared), _f("minor", unique_minor[name])],
        )
        for name in ("a", "b", "c")
    ]
    truncated_score = truncating.evaluate(reviewers).disagreement
    full_score = no_trunc.evaluate(reviewers).disagreement
    # Truncation drops the 3 minor singletons; full counts them.
    assert truncated_score < full_score


def test_v2_critical_singletons_survive_truncation():
    """A lone reviewer flagging a critical is signal, not noise. Truncation
    must keep critical singletons in the entropy computation."""
    gate = EntropyGateV2(
        embedder=HashEmbedder(),
        threshold=0.30,
        min_cluster_size=2,
        consensus_override_min=2.0,
    )
    shared = "shared nit cosmetic style preference low severity"
    unique_crit = {
        "a": "alpha bravo charlie delta",
        "b": "foxtrot golf hotel india",
        "c": "kilo lima mike november",
    }
    reviewers = [
        _review_with(
            name,
            [_f("nit", shared), _f("critical", unique_crit[name])],
        )
        for name in ("a", "b", "c")
    ]
    v = gate.evaluate(reviewers)
    assert v.verdict == Verdict.ESCALATE


def test_v2_all_singletons_keeps_max_disagreement():
    """The edge case: when every reviewer raises a unique critical (no
    shared cluster at all), don't truncate them — that's genuine maximum
    disagreement, not noise."""
    gate = EntropyGateV2(
        embedder=HashEmbedder(),
        threshold=0.30,
        min_cluster_size=2,
        consensus_override_min=2.0,
    )
    reviewers = [
        _review_with("a", [_f("critical", "auth bypass token flaw issue")]),
        _review_with("b", [_f("critical", "data corruption schema migration")]),
        _review_with("c", [_f("critical", "race condition lock acquisition")]),
    ]
    v = gate.evaluate(reviewers)
    assert v.verdict == Verdict.ESCALATE
    assert v.disagreement > 0.9


def test_v2_override_validators():
    with pytest.raises(ValueError):
        EntropyGateV2(embedder=HashEmbedder(), consensus_override_min=-0.1)
    with pytest.raises(ValueError):
        EntropyGateV2(embedder=HashEmbedder(), min_cluster_size=0)


def test_v2_disjoint_nits_score_far_below_disjoint_criticals():
    """The whole point of option C: severity density dampens nit disagreement.
    Three reviewers each raising a different nit should score MUCH lower than
    three reviewers each raising a different critical."""
    gate = EntropyGateV2(embedder=HashEmbedder())
    nits = [
        _review_with("a", [_f("nit", "trailing whitespace style nit")]),
        _review_with("b", [_f("nit", "import ordering convention nit")]),
        _review_with("c", [_f("nit", "variable naming preference nit")]),
    ]
    crits = [
        _review_with("a", [_f("critical", "auth bypass token validation flaw")]),
        _review_with("b", [_f("critical", "data corruption migration schema")]),
        _review_with("c", [_f("critical", "race condition lock acquisition")]),
    ]
    nit_score = gate.evaluate(nits).disagreement
    crit_score = gate.evaluate(crits).disagreement
    # Both have max entropy (uniform over 3 clusters). The difference comes
    # entirely from severity density: 0.25/4.0 vs 4.0/4.0 = 16x.
    assert crit_score > 0.9
    assert nit_score < 0.1
    assert crit_score / max(nit_score, 1e-6) > 10


def _with_overall(r: Review, rec) -> Review:
    r.overall = OverallVerdict(recommendation=rec, severity="major")
    return r


def test_v1_polar_recommendation_split_escalates():
    gate = EntropyGate(threshold=0.35)
    same = "null check missing in parser line forty two"
    a = _with_overall(_review("openai", [same]), "accept")
    b = _with_overall(_review("anthropic", [same]), "block")
    v = gate.evaluate([a, b])
    assert v.verdict == Verdict.ESCALATE
    assert "conflict" in v.reason
    assert set(v.recommendations) == {"accept", "block"}


def test_v1_unanimous_block_is_not_forced_escalation():
    gate = EntropyGate(threshold=0.35)
    same = "null check missing in parser line forty two"
    a = _with_overall(_review("openai", [same]), "block")
    b = _with_overall(_review("anthropic", [same]), "block")
    v = gate.evaluate([a, b])
    assert v.verdict == Verdict.CONSENSUS_CHECK
    assert v.recommendations == ("block", "block")


def test_v2_polar_split_vetoes_consensus_override():
    gate = EntropyGateV2(
        embedder=HashEmbedder(), threshold=0.30, consensus_override_min=0.80
    )
    shared = "unbounded recursion in config loader"
    reviews = [
        _with_overall(_review_with(p, [_f("critical", shared)]), rec)
        for p, rec in (("a", "block"), ("b", "accept"), ("c", "block"))
    ]
    v = gate.evaluate(reviews)
    assert v.verdict == Verdict.ESCALATE
    assert "conflict" in v.reason


def test_v2_unanimous_serious_cluster_still_overrides_without_split():
    gate = EntropyGateV2(
        embedder=HashEmbedder(), threshold=0.30, consensus_override_min=0.80
    )
    shared = "unbounded recursion in config loader"
    reviews = [
        _with_overall(_review_with(p, [_f("critical", shared)]), "block")
        for p in ("a", "b", "c")
    ]
    v = gate.evaluate(reviews)
    assert v.verdict == Verdict.CONSENSUS_CHECK
    assert v.recommendations == ("block", "block", "block")


def test_v2_clean_reviews_with_polar_split_escalate_not_insufficient():
    gate = EntropyGateV2(embedder=HashEmbedder())
    a = _with_overall(Review(model_id="a/m", provider="a", findings=[], raw_text="{}"), "accept")
    b = _with_overall(Review(model_id="b/m", provider="b", findings=[], raw_text="{}"), "block")
    v = gate.evaluate([a, b])
    assert v.verdict == Verdict.ESCALATE
    assert "conflict" in v.reason


def test_v2_revise_vs_block_is_not_polar():
    gate = EntropyGateV2(embedder=HashEmbedder(), consensus_override_min=0.80)
    shared = "unbounded recursion in config loader"
    reviews = [
        _with_overall(_review_with(p, [_f("critical", shared)]), rec)
        for p, rec in (("a", "block"), ("b", "revise"))
    ]
    v = gate.evaluate(reviews)
    assert v.verdict == Verdict.CONSENSUS_CHECK


def test_insufficient_still_records_lone_recommendation():
    gate = EntropyGate(threshold=0.35)
    r = _with_overall(_review("openai", ["single reviewer finding here"]), "block")
    v = gate.evaluate([r])
    assert v.verdict == Verdict.INSUFFICIENT
    assert v.recommendations == ("block",)
