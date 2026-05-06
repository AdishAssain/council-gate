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

    # Build the markdown report into a string.
    report = _build_markdown_report(args, v, reviews, redaction_count)

    # Auto-save unless --no-save. Filename is timestamp-tagged so successive
    # runs don't clobber each other.
    if not args.no_save:
        from datetime import datetime
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        out_path = Path.cwd() / f"council-gate-{args.artifact.stem}-{stamp}.md"
        out_path.write_text(report, encoding="utf-8")
        print(f"\nreport saved → {out_path}", file=sys.stderr)
        print(f"verdict: {v.verdict.value}  ·  disagreement: {v.disagreement:.2f}", file=sys.stderr)

    if args.print or args.no_save:
        # Always print to stdout if --print was passed, or if save was disabled.
        sys.stdout.write(report)

    return 0


def _build_markdown_report(
    args: argparse.Namespace,
    v: GateVerdict,
    reviews: list[Review],
    redaction_count: int,
) -> str:
    """Markdown report aimed at a non-coder PM / Director of AI reader.

    Plain-English verdict, TL;DR, findings, errored seats, next steps.
    No jargon ("entropy gate", "asymmetric"); no stack traces.
    """
    from datetime import datetime
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as pkg_version

    try:
        cg_version = pkg_version("council-gate")
    except PackageNotFoundError:
        cg_version = "unknown"

    ok = [r for r in reviews if r.ok]
    failed = [r for r in reviews if not r.ok]
    out: list[str] = []

    # ─── Header ──────────────────────────────────────────────────────────
    out.append(f"# Council review — `{args.artifact.name}`\n")

    if v.verdict == Verdict.ESCALATE:
        headline = (
            "**The council disagreed.** Reviewers did not converge on a single set "
            "of findings. **Read the individual reviews below before acting.**"
        )
    elif v.verdict == Verdict.CONSENSUS_CHECK:
        headline = (
            "**The council reached consensus** — but consensus is not approval. "
            "Frontier AI models often share blindspots, so use the verification "
            "checklist below before treating this as a clean review."
        )
    else:
        headline = (
            "**Inconclusive review.** Too few reviewers returned usable output to "
            "form a verdict. See the *Errored seats* section for details."
        )
    out.append(f"{headline}\n")

    # ─── TL;DR table ─────────────────────────────────────────────────────
    out.append("## At a glance\n")
    out.append("| | |")
    out.append("|---|---|")
    out.append(f"| **Verdict** | `{v.verdict.value}` |")
    out.append(f"| **Reviewers** | {len(ok)} returned reviews · {len(failed)} errored |")
    out.append(
        f"| **Disagreement** | {v.disagreement:.2f} on a 0–1 scale "
        f"(threshold {args.threshold:.2f}; higher = more divergence) |"
    )
    out.append(f"| **Mode** | {args.mode} |")
    if redaction_count:
        out.append(
            f"| **Privacy** | {redaction_count} secret-shaped substring(s) were "
            f"redacted from the artifact before it reached any model |"
        )
    out.append("")

    # ─── Successful reviews ──────────────────────────────────────────────
    if ok:
        out.append("## What each reviewer said\n")
        for r in ok:
            out.append(f"### {r.model_id}\n")
            if r.findings:
                out.append("| Severity | Where | Issue |")
                out.append("|---|---|---|")
                for f in r.findings:
                    loc = f.location or "—"
                    summary = f.summary.replace("|", "\\|")
                    out.append(
                        f"| **{f.severity.upper()}** | `{loc}` | {summary} |"
                    )
                out.append("")
            else:
                out.append("_(reviewer returned free-prose feedback rather than tagged findings)_\n")
            if r.raw_text and not r.findings:
                # Only show raw text when no parsed findings — otherwise the table is the answer
                out.append("<details>\n<summary>Raw response</summary>\n")
                out.append("\n```")
                snippet = r.raw_text[:2000]
                out.append(snippet)
                if len(r.raw_text) > 2000:
                    out.append(f"\n\n[output truncated; {len(r.raw_text) - 2000} more characters]")
                out.append("```\n")
                out.append("</details>\n")
            elif r.raw_text:
                out.append("<details>\n<summary>Raw response (full text the model returned)</summary>\n")
                out.append("\n```")
                snippet = r.raw_text[:2000]
                out.append(snippet)
                if len(r.raw_text) > 2000:
                    out.append(f"\n\n[output truncated; {len(r.raw_text) - 2000} more characters]")
                out.append("```\n")
                out.append("</details>\n")

    # ─── Verdict-specific guidance ───────────────────────────────────────
    if v.verdict == Verdict.CONSENSUS_CHECK:
        out.append("## Verify before trusting consensus\n")
        out.append(
            "Spot-check the council's output against these dimensions, where "
            "frontier AI models statistically tend to agree but be wrong together:\n"
        )
        for d in CORRELATED_BLINDSPOT_DIMENSIONS:
            out.append(f"- {d}")
        out.append("")
    elif v.verdict == Verdict.ESCALATE:
        out.append("## What to do now\n")
        out.append(
            "1. Skim the findings table for each reviewer above.\n"
            "2. Look for any concern flagged by **two or more** reviewers — those are higher-signal.\n"
            "3. Open the artifact yourself and sanity-check whether each finding holds.\n"
            "4. If the disagreement reflects different valid framings, decide which framing matches the artifact's actual purpose.\n"
        )

    # ─── Errored seats ───────────────────────────────────────────────────
    if failed:
        out.append("## Errored seats (no review returned)\n")
        out.append("| Seat | Reason |")
        out.append("|---|---|")
        for r in failed:
            reason = (r.error or "unknown error").replace("|", "\\|")
            # Strip the model_id prefix from the reason since it's in the row label
            if reason.startswith(f"{r.model_id}: "):
                reason = reason[len(r.model_id) + 2 :]
            # Truncate long stderr / tracebacks
            reason = reason if len(reason) < 200 else reason[:200] + "…"
            out.append(f"| `{r.model_id}` | {reason} |")
        out.append("")
        out.append(
            "If the same provider keeps erroring (e.g. 402 Payment Required), "
            "either top up your OpenRouter balance or remove that model from "
            "`COUNCIL_MODELS` in `~/.config/council-gate/.env`.\n"
        )

    # ─── Run details (non-essential, last) ───────────────────────────────
    out.append("---")
    out.append("\n_Run details_\n")
    out.append(f"- Tool: `council-gate v{cg_version}`")
    out.append(
        f"- Run at: {datetime.now(UTC).isoformat(timespec='seconds')}"
    )
    out.append(f"- Threshold: {args.threshold:.2f}")
    out.append(f"- Reason: {v.reason}")
    out.append("")
    return "\n".join(out)


def main() -> int:
    # Friendly default: WARN, no httpx noise. --verbose lifts to DEBUG.
    logging.basicConfig(
        level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s"
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
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
    review.add_argument(
        "--no-save",
        action="store_true",
        help="Skip auto-saving the markdown report to a file in cwd. "
        "Output goes to stdout instead.",
    )
    review.add_argument(
        "--print",
        action="store_true",
        help="In addition to saving the report, also print it to stdout.",
    )
    review.add_argument(
        "--verbose",
        action="store_true",
        help="Show DEBUG-level logs (HTTP requests, parsing diagnostics).",
    )

    args = p.parse_args()
    if getattr(args, "verbose", False):
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger("httpx").setLevel(logging.INFO)
    if args.command == "init":
        return _cmd_init(args)
    if args.command == "review":
        return _cmd_review(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
