import argparse
import logging
import os
import re
import sys
from datetime import UTC
from importlib.resources import files
from pathlib import Path

from dotenv import load_dotenv

from council_gate.council import Council
from council_gate.escalation import format_escalation
from council_gate.gate import (
    CORRELATED_BLINDSPOT_DIMENSIONS,
    EntropyGate,
    GateVerdict,
    Verdict,
)
from council_gate.providers import CodexProvider, OpenRouterProvider, Provider
from council_gate.redaction import RefusedFilename, check_filename, redact
from council_gate.types import Review

BUNDLED_MODES = ("eng", "proposal", "analysis", "general")


def _config_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return base / "council-gate" / ".env"


def _load_env() -> None:
    """XDG-compliant env loading. Never reads from cwd — installed tools
    must not depend on the user's working directory."""
    explicit = os.environ.get("COUNCIL_GATE_ENV")
    if explicit and Path(explicit).is_file():
        load_dotenv(explicit, override=False)
        return
    p = _config_path()
    if p.is_file():
        load_dotenv(p, override=False)


def _build_seats() -> list[Provider]:
    seats: list[Provider] = []
    if os.environ.get("OPENROUTER_API_KEY"):
        models = [
            m.strip()
            for m in os.environ.get("COUNCIL_MODELS", "").split(",")
            if m.strip()
        ]
        seats.extend(OpenRouterProvider(m) for m in models)
    if os.environ.get("COUNCIL_INCLUDE_CODEX", "1") == "1":
        try:
            seats.append(CodexProvider())
        except RuntimeError as e:
            logging.getLogger("council_gate.cli").info(
                "codex CLI seat skipped: %s. Install + auth codex if you want it on the council.",
                e,
            )
    return seats


def _load_prompt(mode: str | None, prompt_path: Path | None) -> str:
    if prompt_path:
        return prompt_path.read_text(encoding="utf-8")
    mode = mode or "eng"
    if mode not in BUNDLED_MODES:
        raise SystemExit(
            f"unknown mode {mode!r}; choose from {BUNDLED_MODES} or pass --prompt"
        )
    return (
        files("council_gate._assets")
        .joinpath(f"{mode}_review.md")
        .read_text(encoding="utf-8")
    )


def _cmd_init(args: argparse.Namespace) -> int:
    target = _config_path()
    if target.exists() and not args.force:
        print(
            f"council-gate: {target} already exists. Pass --force to overwrite, "
            f"or edit it directly.",
            file=sys.stderr,
        )
        return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    template = (
        files("council_gate._assets").joinpath("env.example").read_text(encoding="utf-8")
    )

    key = args.openrouter_key
    if key is None and sys.stdin.isatty():
        # Interactive: prompt once. Visible (not getpass) because OpenRouter
        # keys are not high-blast-radius and visible input is friendlier for
        # non-coding users who paste from a browser tab.
        try:
            key = input(
                "OpenRouter API key (paste from https://openrouter.ai/keys, "
                "or press Enter to skip and edit later): "
            ).strip() or None
        except (EOFError, KeyboardInterrupt):
            key = None

    if key:
        # Substitute the empty OPENROUTER_API_KEY= line with the key.
        template = re.sub(
            r"^OPENROUTER_API_KEY=.*$",
            f"OPENROUTER_API_KEY={key}",
            template,
            count=1,
            flags=re.MULTILINE,
        )

    target.write_text(template)
    target.chmod(0o600)
    print(f"wrote {target} (chmod 600)")
    if key:
        print("OpenRouter key set. Try: council-gate review <some-file>.md")
    else:
        print(
            "No key set. Edit the file with one of:\n"
            f"  open -e {target}        # TextEdit (macOS)\n"
            f"  nano {target}           # terminal editor\n"
            f"  code {target}           # VS Code"
        )
    return 0


def _cmd_review(args: argparse.Namespace) -> int:
    if not args.artifact.is_file():
        print(f"council-gate: artifact not found: {args.artifact}", file=sys.stderr)
        return 2
    if not args.skip_redaction_check:
        try:
            check_filename(args.artifact)
        except RefusedFilename as e:
            print(f"council-gate: {e}", file=sys.stderr)
            return 3
    raw_text = args.artifact.read_text(encoding="utf-8")
    artifact_text, redaction_count = (
        (raw_text, 0) if args.skip_redaction_check else redact(raw_text)
    )
    if redaction_count:
        logging.getLogger("council_gate.cli").warning(
            "redacted %d secret-shaped substring(s) from artifact before dispatch",
            redaction_count,
        )
    system_prompt = _load_prompt(args.mode, args.prompt)

    seats = _build_seats()
    if not seats:
        print(
            "council-gate: no seats configured. First run? Try:\n"
            "  council-gate init                     # writes ~/.config/council-gate/.env\n"
            "  $EDITOR ~/.config/council-gate/.env   # set OPENROUTER_API_KEY\n",
            file=sys.stderr,
        )
        return 2
    council = Council(seats, generator_provider=args.generator_provider)
    if len(council.seats) < 2:
        print(
            f"council-gate: need >=2 seats post-exclusion (have {len(council.seats)}). "
            "Add more diverse providers to COUNCIL_MODELS in "
            "~/.config/council-gate/.env, or install codex CLI for an extra seat.",
            file=sys.stderr,
        )
        return 2

    reviews = council.run(artifact_text, system_prompt)
    gate = EntropyGate(threshold=args.threshold)
    v = gate.evaluate(reviews)
    _render_markdown(args, v, reviews, redaction_count)
    return 0


def _render_markdown(
    args: argparse.Namespace,
    v: GateVerdict,
    reviews: list[Review],
    redaction_count: int,
) -> None:
    """Print a markdown-formatted report to stdout.

    Designed so `council-gate review … | tee output.md` produces a file
    that renders cleanly in any markdown viewer (Cursor, VS Code, GitHub).
    """
    from datetime import datetime

    print(f"# council-gate review — {args.artifact.name}\n")
    print(f"- **Verdict:** `{v.verdict.value}`")
    print(f"- **Disagreement:** {v.disagreement:.3f} (threshold {args.threshold:.2f})")
    print(f"- **Reviewers:** {v.reviewer_count} succeeded out of {len(reviews)}")
    print(f"- **Mode:** `{args.mode}`")
    print(
        f"- **Run at:** {datetime.now(UTC).isoformat(timespec='seconds')}"
    )
    if redaction_count:
        print(
            f"- **Redaction:** {redaction_count} secret-shaped substring(s) "
            f"scrubbed from artifact before dispatch"
        )
    print(f"\n> {v.reason}\n")

    if v.verdict == Verdict.ESCALATE:
        print("## Escalation message\n")
        print(
            "Paste this into your team channel (PR comment, Slack, WhatsApp). "
            "Verbatim — the divergence detail is the value.\n"
        )
        print(format_escalation(args.artifact.name, v, reviews, args.threshold))
        print()
    elif v.verdict == Verdict.CONSENSUS_CHECK:
        print("## Verify before trusting consensus\n")
        print(
            "Consensus reached, but the gate is asymmetric: low disagreement is "
            "treated as *suspect consensus*, not approval. Frontier models share "
            "blindspots. Spot-check the council's output against these dimensions:\n"
        )
        for d in CORRELATED_BLINDSPOT_DIMENSIONS:
            print(f"- {d}")
        print()

    print("## Per-reviewer output\n")
    for r in reviews:
        status = "✓" if r.ok else "✗"
        print(f"### {status} `{r.model_id}` ({r.provider})\n")
        if r.error:
            print(f"**Error:** `{r.error}`\n")
            continue
        if r.findings:
            print("**Parsed findings:**\n")
            for f in r.findings:
                loc = f" `{f.location}`" if f.location else ""
                print(f"- **{f.severity.upper()}**{loc} — {f.summary}")
            print()
        print("**Raw output:**\n")
        print("```")
        print(r.raw_text[:1500])
        if len(r.raw_text) > 1500:
            print(
                f"\n[output truncated; {len(r.raw_text) - 1500} more chars not shown]"
            )
        print("```\n")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    _load_env()

    p = argparse.ArgumentParser(prog="council-gate")
    sub = p.add_subparsers(dest="command", required=True)

    init = sub.add_parser(
        "init",
        help="Write ~/.config/council-gate/.env. Prompts for OpenRouter key if interactive.",
    )
    init.add_argument(
        "--openrouter-key",
        default=None,
        help="OpenRouter API key. Skips the interactive prompt.",
    )
    init.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing config file.",
    )

    review = sub.add_parser("review", help="Run the council on an artifact.")
    review.add_argument("artifact", type=Path)
    review.add_argument(
        "--mode",
        choices=BUNDLED_MODES,
        default="eng",
        help="Bundled review prompt to use (default: eng).",
    )
    review.add_argument(
        "--prompt",
        type=Path,
        default=None,
        help="Override --mode with a custom prompt file.",
    )
    review.add_argument(
        "--generator-provider",
        default=os.environ.get("COUNCIL_GENERATOR_PROVIDER"),
        help="Provider slug to exclude from the council (the artifact's author).",
    )
    review.add_argument(
        "--threshold",
        type=float,
        default=float(os.environ.get("GATE_THRESHOLD", "0.35")),
    )
    review.add_argument(
        "--skip-redaction-check",
        action="store_true",
        help="Bypass secret-bearing-filename refusal and inline redaction. "
        "Only use if you're sure the artifact contains no secrets.",
    )

    args = p.parse_args()
    if args.command == "init":
        return _cmd_init(args)
    if args.command == "review":
        return _cmd_review(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
