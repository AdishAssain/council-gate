---
description: Run a cross-model council review on a document, proposal, or PR diff
argument-hint: <path-to-file>
---

You are running `council-gate` on behalf of the user. The artifact path is: `$ARGUMENTS`

## Step 1 — verify the file exists

If `$ARGUMENTS` is empty or the file does not exist, ask the user for the path. Don't proceed without one.

## Step 2 — check setup

Run this Bash command (silently — capture output only):

```
uvx --from git+https://github.com/AdishAssain/council-gate council-gate doctor
```

Read the output. If it reports `OpenRouter key: missing`, then **before** running the review:
1. Ask the user (in chat): "I need an OpenRouter API key to run the council. Get one at https://openrouter.ai/keys (free tier works) and paste it here."
2. When they paste the key (starts with `sk-or-v1-...`), run:
   ```
   uvx --from git+https://github.com/AdishAssain/council-gate council-gate init --openrouter-key <THEIR_KEY>
   ```
3. Confirm setup with `council-gate doctor` again before continuing.

## Step 3 — run the review

```
uvx --from git+https://github.com/AdishAssain/council-gate council-gate review "$ARGUMENTS"
```

The command auto-saves a markdown report to the current directory (`./council-gate-<stem>-<timestamp>.md`) and prints a one-line verdict to stderr.

## Step 4 — surface the report

After the command completes successfully, find the saved report file (it'll match `council-gate-*.md`, newest one) and:

1. Read the report.
2. Summarize for the user in 3–5 sentences: **verdict** (escalate / consensus_check / inconclusive), **disagreement score**, and the **top 2-3 findings** that multiple reviewers flagged.
3. Tell them where the full report is saved so they can open it.

If the command fails, surface the friendly error message verbatim — `council-gate` is designed to print actionable plain-English errors. Don't translate or re-interpret; the tool's own messages are the answer.

## Notes

- Mode is auto-selected: `.docx`/`.pdf`/`.odt` → `proposal` review; everything else → `eng`. The user can override by adding `--mode {eng,proposal,analysis,general}` to the command.
- Supported formats: `.docx`, `.pdf`, `.pptx`, `.xlsx`, `.odt`, `.rtf`, `.epub`, `.md`, `.diff`, `.patch`, source code in any language.
- The artifact is redacted for secrets before any model sees it.
