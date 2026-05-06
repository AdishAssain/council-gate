import pytest

from council_gate.gate import EntropyGate, Verdict
from council_gate.types import Finding, Review


def _review(provider: str, summaries: list[str]) -> Review:
    return Review(
        model_id=f"{provider}/test",
        provider=provider,
        findings=[Finding(severity="major", summary=s) for s in summaries],
        raw_text=" ".join(summaries),
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
