from council_gate.escalation import format_escalation
from council_gate.gate import GateVerdict, Verdict
from council_gate.types import Finding, Review


def _r(provider: str, summary: str) -> Review:
    return Review(
        model_id=f"{provider}/x",
        provider=provider,
        findings=[Finding(severity="major", summary=summary)],
        raw_text=summary,
    )


def test_format_escalation_lists_each_reviewer():
    verdict = GateVerdict(
        verdict=Verdict.ESCALATE, disagreement=0.78, reviewer_count=2, reason="..."
    )
    reviews = [_r("openai", "auth bug in handler"), _r("anthropic", "perf in loop")]
    out = format_escalation("spec.md", verdict, reviews, threshold=0.35)
    assert "spec.md" in out
    assert "0.78" in out
    assert "openai" in out and "anthropic" in out
    assert "auth bug" in out and "perf in loop" in out
