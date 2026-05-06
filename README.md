# council-gate

[![CI](https://github.com/AdishAssain/council-gate/actions/workflows/test.yml/badge.svg)](https://github.com/AdishAssain/council-gate/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![PyPI](https://img.shields.io/badge/install-uv%20tool-orange)](https://github.com/astral-sh/uv)

> Cross-model adversarial review with an asymmetric entropy gate.

`council-gate` runs any artifact — `.docx` proposal, `.pdf` report, engineering spec, PR diff, data analysis, strategy doc — past a council of frontier LLMs from **different providers**, measures cross-reviewer disagreement, and routes the result to one of two destinations:

- **High disagreement** → a formatted escalation message ready for human adjudication.
- **Low disagreement** → a consensus report annotated with **known correlated-failure dimensions** the council is statistically likely to have missed together.

The two original primitives are the **council** (cross-model, not cross-prompt) and the **entropy gate** (asymmetric — only *high* disagreement is a clean signal; *low* disagreement is treated as suspect, not as approval).

```
                  artifact (spec / diff / plan)
                              │
                              ▼
        ┌──────────────────  Council  ──────────────────┐
        │  Adapter A      Adapter B      Adapter C       │  (different providers,
        │  e.g. Claude    e.g. GPT       e.g. Gemini     │   generator excluded)
        └────────┬───────────┬───────────────┬───────────┘
                 │           │               │
                 ▼           ▼               ▼
                Review      Review          Review        (structured findings + raw)
                              │
                              ▼
                       Entropy Gate
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
     disagreement ≥ τ                disagreement < τ
              │                               │
              ▼                               ▼
        ESCALATE                      CONSENSUS_CHECK
   (formatted message               (verify against known
    for human channel)               correlated blindspots)
```

## What you can review

**Supported formats** (no flags, auto-detected):

- **Documents**: `.docx`, `.pdf`, `.pptx`, `.xlsx`, `.odt`, `.rtf`, `.epub` — converted to markdown via [MarkItDown](https://github.com/microsoft/markitdown)
- **Plain text**: `.md`, `.txt`, `.diff`, `.patch`, source code in any language — read verbatim

Pick the `--mode` that matches your artifact, or let it auto-pick (`.docx`/`.pdf` → `proposal`, everything else → `eng`). The mode changes *what the council looks for*, not how disagreement is measured.

| `--mode` | Use it for | Focus |
|---|---|---|
| `eng` | engineering specs, PR diffs, design docs, plans | correctness, edge cases, failure modes, missing-data handling, security boundaries, silent-failure paths |
| `proposal` | grant proposals, strategy docs, pitches, research statements | claim/evidence asymmetry, hidden assumptions, audience fit, vague language, missing failure modes |
| `analysis` | data analyses, research findings, statistical claims | sample bias, confounders, missing-data handling, unsupported causal claims, statistical pitfalls, reproducibility |
| `general` | other / mixed / fallback | factual errors, internal inconsistencies, unsupported claims, hidden assumptions |

Bring your own prompt with `--prompt path/to/your.md` for fully bespoke reviews.

> **`council-gate` command not found after restarting your terminal?** Run `~/.local/bin/council-gate doctor` for setup diagnostics, or re-run `council-gate init` to repair your PATH (now writes both `.zshrc` and `.zprofile`).

## Why cross-model, not cross-prompt

Same-model self-evaluation is biased. [Panickssery et al. (2024)](https://arxiv.org/abs/2404.13076) showed that LLM evaluators recognise and favour their own generations — the bias is consistent and measurable, not stylistic. A "council" of three Claude personas reviewing Claude-generated code is doing performance, not adversarial work.

`council-gate` enforces this with one rule: **the generator is excluded from the council.** Host integrations declare which provider produced the artifact via `COUNCIL_GENERATOR_PROVIDER`, and that provider's seats are dropped before the council runs.

## Why the gate is asymmetric

The naive design — *low entropy means trust, high entropy means escalate* — is half wrong.

[Kim et al. (2025)](https://arxiv.org/abs/2506.07962) studied 350+ LLMs and found that models agree roughly **60% of the time when both err**. Their reported inter-model error correlation of r ≈ 0.77 implies an effective ensemble size of ~1.3 from three models — barely more diversified than asking one. The drivers are unsurprising in retrospect: shared providers, shared architectures, and **shared capability tier**. Larger frontier models are *more* correlated even across providers, not less, because they converge on similar training distributions and post-training patterns.

[Shin et al. (2025)](https://arxiv.org/abs/2502.17086) sharpened this with a specific finding: frontier LLMs systematically over-weight technical validity and under-weight novelty when reviewing scientific work. A shared blindspot, not random noise.

The gate handles this asymmetrically:

| Council output    | Naive read                      | `council-gate` read                                                                       |
| ----------------- | ------------------------------- | ----------------------------------------------------------------------------------------- |
| High disagreement | "Bad — humans must adjudicate." | Correct. Format the escalation.                                                           |
| Low disagreement  | "Good — auto-proceed."          | Treat as *suspect consensus*. Surface the known correlated-failure dimensions explicitly. |

In practice, low-disagreement output ships with a checklist (`novelty`, `edge cases`, `failure modes`, `missing-data handling`, `long-term maintenance`) for the human to verify against, rather than a green check.

## Quickstart

Requires Python ≥ 3.12 and [`uv`](https://docs.astral.sh/uv/).

```bash
uv tool install git+https://github.com/AdishAssain/council-gate
council-gate init --openrouter-key sk-or-v1-…   # interactive prompt if you skip the flag
council-gate review path/to/artifact.md          # auto-saves clean markdown report to cwd
```

That's it. The report lands at `./council-gate-<artifact>-<timestamp>.md` ready to open in any markdown viewer (Cursor, VS Code, GitHub).

### Other commands

| Command | What it does |
|---|---|
| `council-gate init [--openrouter-key …]` | Writes `~/.config/council-gate/.env`. Interactive prompt for the key. Offers to add `~/.local/bin` to your PATH if missing. |
| `council-gate review <file> [--mode {eng,proposal,analysis,general}]` | Runs the council on the artifact. Auto-saves a clean markdown report. `--no-save` for stdout-only; `--print` for both. |
| `council-gate doctor` | Diagnoses common setup issues: config present, key set, PATH on, codex CLI available. |
| `council-gate update` | Pulls the latest from GitHub and reinstalls. One-liner instead of remembering the long uv invocation. |

### Configuration

Lives at `~/.config/council-gate/.env` (XDG-compliant). `council-gate` never reads from the working directory; nothing lands in your repo.

Three keys matter:

- `COUNCIL_MODELS` — comma-separated OpenRouter model ids. Default is **cost-conscious** (Haiku, GPT-mini, Gemini Flash, Llama, Qwen, DeepSeek) — works on a $1-2 OpenRouter balance. Swap in flagship variants for higher-stakes reviews; see commented alternatives in `.env`.
- `COUNCIL_GENERATOR_PROVIDER` — slug (`anthropic`, `openai`, `google`) of whichever model produced the artifact. The corresponding seats are excluded from the council.
- `GATE_THRESHOLD` — disagreement threshold τ ∈ [0, 1] above which the gate fires escalation. Default 0.35.

For a council seat that includes the OpenAI Codex CLI, install and authenticate `codex` separately ([openai/codex](https://github.com/openai/codex)).

## Integrations

`council-gate` is a CLI; host integrations are thin wrappers that set `COUNCIL_GENERATOR_PROVIDER` before invoking it.

- **Claude Code** — `integrations/claude-code/`
- **Codex CLI** — `integrations/codex/`
- **GitHub Action** — `integrations/github-action/`

Each is a copy-paste install. None require modifying `council-gate` itself.

## Configuration

Three keys matter:

- `COUNCIL_MODELS` — comma-separated OpenRouter model ids. Diversity matters more than count; mix providers and capability tiers.
- `COUNCIL_GENERATOR_PROVIDER` — provider slug (`anthropic`, `openai`, `google`) of whichever model produced the artifact. Set by host integrations; can be overridden with `--generator-provider`.
- `GATE_THRESHOLD` — disagreement threshold τ ∈ [0, 1] above which the gate fires escalation. Default 0.35.

See `src/council_gate/_assets/env.example` for the full schema.

## How disagreement is measured

Pairwise Jaccard distance over normalized token sets extracted from each reviewer's findings, averaged across reviewer pairs. The metric measures lexical overlap, not semantic agreement — sufficient for the asymmetric gate's purpose, since high disagreement still means high disagreement, and low disagreement is *already* treated as suspect rather than as approval.

## Privacy and secret-leak guardrails

`council-gate` sends the artifact body to the LLM APIs of every council seat. Three layers of protection ship by default:

1. **Filename refusal.** The CLI refuses to read files matching obvious secret-bearing patterns (`.env`, `.pem`, `.key`, `id_rsa`, `*credentials*`, `*secret*`, `*.gpg`, `*.kdbx`).
2. **Inline redaction.** The artifact body is scanned for known secret patterns (OpenAI/Anthropic/Google/AWS/Slack/GitHub keys, JWTs, PEM private-key blocks) and redacted with `[REDACTED:...]` placeholders before any model sees it. Redaction count is logged.
3. **Disclosure.** This section. Don't pass files containing secrets, PII, or confidential third-party data. The redaction layer is defence in depth, not a substitute for judgement.

To bypass both, pass `--skip-redaction-check`. Don't use this flag unless you've audited the artifact yourself.

## Related work

- Panickssery, A., Bowman, S. R., & Feng, S. (2024). *LLM Evaluators Recognize and Favor Their Own Generations.* NeurIPS 2024. [arXiv:2404.13076](https://arxiv.org/abs/2404.13076)
- Kim, E., Garg, A., Peng, K., & Garg, N. (2025). *Correlated Errors in Large Language Models.* ICML 2025. [arXiv:2506.07962](https://arxiv.org/abs/2506.07962)
- Shin, H. et al. (2025). *Mind the Blind Spots: A Focus-Level Evaluation Framework for LLM Reviews.* EMNLP 2025 (Oral). [arXiv:2502.17086](https://arxiv.org/abs/2502.17086)

## Contributor install

```bash
git clone https://github.com/AdishAssain/council-gate.git
cd council-gate
uv sync --extra dev
uv run pre-commit install      # runs ruff + pytest before each commit
uv run pytest
```

CI runs `ruff check`, `pytest`, and a wheel-build sanity check on every push and PR (`.github/workflows/test.yml`). The pre-commit hooks catch most failures locally before they hit CI.

## License

MIT. See [LICENSE](LICENSE).
