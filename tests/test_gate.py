"""Learned gate: feature extraction, scoring math, verdict logic."""
import pytest

from council_gate.gate import (
    GATE_MODELS,
    LearnedGate,
    Verdict,
    _features,
    _score_gb,
    _score_linear,
)
from council_gate.types import Finding, OverallVerdict, Review


def _review(provider, findings, rec=None):
    return Review(
        model_id=f"{provider}/test",
        provider=provider,
        findings=findings,
        raw_text="x",
        overall=OverallVerdict(recommendation=rec, severity="major") if rec else None,
    )


def _f(sev="major", disp="defect"):
    return Finding(severity=sev, summary="s", disposition=disp)


def test_all_models_load_and_score():
    reviews = [
        _review("a", [_f("critical")], "revise"),
        _review("b", [_f("major", "gap")], "revise"),
        _review("c", [_f("minor", "endorse")], "accept"),
    ]
    for model in GATE_MODELS:
        v = LearnedGate(model=model).evaluate(reviews)
        assert v.verdict in (Verdict.ESCALATE, Verdict.CONSENSUS_CHECK)
        assert 0.0 <= v.score <= 1.0
        assert v.recommendations == ("revise", "revise", "accept")


def test_insufficient_below_two_reviewers():
    v = LearnedGate().evaluate([_review("a", [_f()], "block")])
    assert v.verdict == Verdict.INSUFFICIENT
    assert v.recommendations == ("block",)


def test_polar_split_escalates_all_models():
    reviews = [
        _review("a", [_f("nit", "endorse")], "accept"),
        _review("b", [_f("nit", "endorse")], "block"),
    ]
    for model in GATE_MODELS:
        v = LearnedGate(model=model).evaluate(reviews)
        assert v.verdict == Verdict.ESCALATE
        assert "conflict" in v.reason


def test_unanimous_accept_is_consensus():
    reviews = [
        _review("a", [_f("nit", "endorse")], "accept"),
        _review("b", [], "accept"),
        _review("c", [_f("minor", "endorse")], "accept"),
        _review("d", [], "accept"),
        _review("e", [], "accept"),
        _review("f", [], "accept"),
    ]
    v = LearnedGate().evaluate(reviews)
    assert v.verdict == Verdict.CONSENSUS_CHECK


def test_reason_names_drivers():
    reviews = [
        _review("a", [_f("critical")], "revise"),
        _review("b", [_f("critical")], "revise"),
    ]
    v = LearnedGate().evaluate(reviews)
    assert "→" in v.reason  # linear model cites contribution directions


def test_features_shape():
    reviews = [
        _review("a", [_f("critical", "defect"), _f("nit", "endorse")], "block"),
        _review("b", [_f("major", "risk")], "accept"),
    ]
    f = _features(reviews)
    assert f["n_findings"] == 3.0
    assert f["n_ok"] == 2.0
    assert f["polar"] == 1.0
    assert f["critical_rate"] == pytest.approx(1 / 3)
    assert f["disp_endorse"] == pytest.approx(1 / 3)
    assert f["rec_block"] == 0.5


def test_score_linear_exact():
    m = {"means": [1.0, 2.0], "stds": [2.0, 4.0], "coefs": [1.0, -1.0], "intercept": 0.5}
    prob, contribs = _score_linear([3.0, 2.0], m)
    # z = 0.5 + 1*(3-1)/2 + (-1)*(2-2)/4 = 1.5
    import math

    assert prob == pytest.approx(1 / (1 + math.exp(-1.5)))
    assert contribs == [1.0, 0.0]


def test_score_gb_exact():
    m = {
        "init_raw": 0.0,
        "learning_rate": 0.5,
        "trees": [
            {"cl": [1, -1, -1], "cr": [2, -1, -1], "feat": [0, -2, -2],
             "thr": [1.0, -2.0, -2.0], "val": [0.0, -2.0, 2.0]}
        ],
    }
    import math

    assert _score_gb([0.5], m) == pytest.approx(1 / (1 + math.exp(1.0)))   # left leaf
    assert _score_gb([1.5], m) == pytest.approx(1 / (1 + math.exp(-1.0)))  # right leaf


def test_unknown_model_rejected():
    with pytest.raises(ValueError):
        LearnedGate(model="v1")
    with pytest.raises(ValueError):
        LearnedGate(threshold=1.5)
