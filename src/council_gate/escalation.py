from importlib.resources import files
from string import Template

from council_gate.gate import GateVerdict
from council_gate.types import Review


def _load_template() -> Template:
    raw = files("council_gate._assets").joinpath("escalation.md").read_text(encoding="utf-8")
    return Template(raw)


def format_escalation(
    artifact_name: str,
    verdict: GateVerdict,
    reviews: list[Review],
    threshold: float,
) -> str:
    # Only successful reviewers contribute to the escalation body — failed
    # seats have nothing to add and pollute the output with empty entries.
    ok = [r for r in reviews if r.ok]
    reviewer_summary = ", ".join(f"{r.provider} ({r.model_id})" for r in ok)
    blocks: list[str] = []
    for r in ok:
        if r.findings:
            bullets = "\n  ".join(
                f"- {f.severity.upper()}: {f.summary}" for f in r.findings
            )
        else:
            snippet = r.raw_text[:300].strip() or "(empty response)"
            bullets = f"- {snippet}"
        blocks.append(f"**{r.provider} ({r.model_id})**\n  {bullets}")
    return _load_template().substitute(
        artifact_name=artifact_name,
        disagreement=f"{verdict.disagreement:.2f}",
        threshold=f"{threshold:.2f}",
        reviewer_summary=reviewer_summary,
        divergence_summary="\n\n".join(blocks),
    )
