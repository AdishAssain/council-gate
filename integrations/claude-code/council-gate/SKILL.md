---
name: council-gate
description: Run cross-model adversarial review of an artifact (spec, PR diff, plan, proposal, analysis). Use when the user asks to "council review", "red team this", "cross-model review", "council gate", or invokes the slash command directly.
---

# council-gate

Runs the `council-gate` CLI against the artifact path the user provides, with `COUNCIL_GENERATOR_PROVIDER=anthropic` so Claude seats are excluded from the council. Output is either an escalation message (high disagreement, ready to paste) or a consensus report annotated with correlated-blindspot dimensions.

## Step 0 — preflight

Before running, check that the user can actually use this. Run these in parallel:

```bash
which council-gate >/dev/null 2>&1 && echo CLI_OK || echo CLI_MISSING
test -f ~/.config/council-gate/.env && echo CONFIG_OK || echo CONFIG_MISSING
```

If `CLI_MISSING`: tell the user to run `uv tool install council-gate` (or `pip install council-gate` / `pipx install council-gate`), then retry the command.

If `CONFIG_MISSING`: run `council-gate init` for them, then ask them to add their `OPENROUTER_API_KEY` to `~/.config/council-gate/.env` and retry.

Do not proceed to Step 1 if either preflight check failed.

## Step 1 — pick the mode

The user's request determines which bundled prompt fits. If the user did not specify, infer from the artifact type:

| Artifact type | `--mode` |
|---|---|
| Spec, PR diff, design doc, plan | `eng` (default) |
| Grant proposal, strategy memo, pitch | `proposal` |
| Data analysis, research finding, statistical claim | `analysis` |
| Other / mixed | `general` |

If the user explicitly named a mode ("review this proposal as a proposal"), use that.

## Step 2 — run

```bash
COUNCIL_GENERATOR_PROVIDER=anthropic council-gate review --mode <mode> "$ARGUMENTS"
```

`$ARGUMENTS` is the file path the user passed.

## Step 3 — interpret the output

Three possible verdicts:

- **`ESCALATE`** → the council disagreed. Paste the printed escalation message into the user's relevant channel (PR comment, Slack, etc.) **verbatim**. Do not summarise — the divergence detail is the value.
- **`CONSENSUS_CHECK`** → the council converged. Surface the printed correlated-blindspot dimensions to the user and explicitly ask which they want to spot-check manually. Do *not* present this as "approved" — the README explains why low-entropy output is treated as suspect rather than approved.
- **`INSUFFICIENT`** → fewer than 2 successful seats, or all reviewers parsed empty. Tell the user to check `OPENROUTER_API_KEY` and `COUNCIL_MODELS` in `~/.config/council-gate/.env`.

If the CLI exits non-zero with a redaction-refusal message (the artifact filename or content matched a secret-bearing pattern), do **not** suggest `--skip-redaction-check` reflexively. Ask the user whether they want to bypass; explain that the body of the artifact will reach external LLM APIs.

## Installation

Copy this directory to `~/.claude/skills/`:

```bash
cp -r integrations/claude-code/council-gate ~/.claude/skills/
```
