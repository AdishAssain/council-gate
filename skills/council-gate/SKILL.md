---
name: council-gate
description: Use when the user asks for a "council review", "second opinion from multiple models", "review this proposal", "review this doc", "review this PR", or wants cross-model adversarial review of any artifact (.docx, .pdf, .md, .diff, source code). Routes consensus and disagreement to explicit channels rather than collapsing to a single answer.
---

# council-gate skill

The user wants a cross-model review of an artifact. Don't try to do this yourself by calling models in sequence — `council-gate` already handles seat orchestration, secret redaction, disagreement scoring, and report formatting.

## When to invoke

Trigger on phrases like:
- "review this proposal / doc / paper / PR"
- "council review"
- "what do multiple models think of this"
- "second opinion on this"
- User drops a `.docx`, `.pdf`, or diff into the conversation and wants feedback

## How to invoke

Use the `/review` slash command if available, or directly run via Bash:

```
uvx council-gate review <PATH>
```

## First-run setup

If `uvx council-gate doctor` reports the OpenRouter key is missing:
1. Tell the user: "I need an OpenRouter API key to run the council. Get one at https://openrouter.ai/keys (free tier works for cheap models)."
2. When they paste a key, run `uvx council-gate init --openrouter-key <key>` to write it to `~/.config/council-gate/.env`.
3. Re-run `uvx council-gate doctor` to confirm.

Always invoke via `uvx council-gate …` (not bare `council-gate …`) inside the plugin context — the user may not have the binary on their PATH.

## Reading the output

The tool auto-saves `council-gate-<stem>-<timestamp>.md` to the cwd. Read that file and summarize for the user:

- **Verdict** is one of: `ESCALATE` (reviewers disagreed — needs human judgment), `CONSENSUS_CHECK` (reviewers agreed — verify against known correlated blindspots), or `INCONCLUSIVE` (too few seats returned usable output).
- **Disagreement** is a 0–1 score; higher = more divergence.
- **Findings tables** list each reviewer's structured concerns with severity.
- The "Verify before trusting consensus" or "What to do now" sections give the user concrete next steps — surface those.

## Don't

- Don't try to substitute your own review for the tool's output. The whole point is that the tool surfaces *cross-model* disagreement, which a single model can't do.
- Don't paraphrase the friendly error messages — they're already plain-English. Surface them verbatim.
- Don't run `council-gate review` on files containing secrets without warning the user; the tool redacts inline secret-shaped substrings but refuses certain filenames (`.env`, `credentials.*`, `*.pem`, etc.).

## Mode selection

Auto-detected by file extension: `.docx`/`.pdf`/`.odt` → `proposal`; source code / diffs / md → `eng`. Override with `--mode {eng,proposal,analysis,general}` only when the file extension misleads (e.g. an `.md` that's actually a grant proposal).
