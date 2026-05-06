# council-gate

[![PyPI](https://img.shields.io/pypi/v/council-gate.svg)](https://pypi.org/project/council-gate/)
[![Python](https://img.shields.io/pypi/pyversions/council-gate.svg)](https://pypi.org/project/council-gate/)
[![CI](https://github.com/AdishAssain/council-gate/actions/workflows/test.yml/badge.svg)](https://github.com/AdishAssain/council-gate/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-ghcr.io-2496ED?logo=docker&logoColor=white)](https://github.com/AdishAssain/council-gate/pkgs/container/council-gate)

> Cross-model adversarial review with an asymmetric entropy gate.
>
> ⚠️ **Pre-stable.** The `1.x` line is functionally complete, but CLI flags / env var names / report format aren't frozen until `2.0`. Pin a version in CI. See [CHANGELOG → Stability](CHANGELOG.md#stability).

**`council-gate` runs your document, proposal, or PR diff past 3+ AI models from different providers (Claude, GPT, Gemini, Llama, …), then tells you where they agree, where they disagree, and what they're statistically likely to have missed together.** Single-model reviews are biased toward their own outputs — consensus from one model isn't a real signal.

---

## Who is this for?

| If you're a… | You hand it… | You get back… |
|---|---|---|
| **Product manager / researcher / grant writer** | a `.docx` proposal, `.pdf` strategy doc, or `.md` brief | a clean markdown report flagging unclear claims, missing failure modes, audience-fit issues, statistical pitfalls — three independent AI editors in one pass |
| **Engineer** | a PR diff, design spec, RFC, or source file | structured findings on edge cases, security boundaries, silent-failure paths — and where reviewers disagreed badly enough that a human should look |

No AI/ML background required. You need a file and ~60 seconds.

---

## Install (one command)

The fastest path on each platform:

| Platform | Command |
|---|---|
| **Python users** | `pip install council-gate` |
| **macOS / Linux / WSL** | `curl -LsSf https://raw.githubusercontent.com/AdishAssain/council-gate/main/install.sh \| sh` |
| **Windows (PowerShell)** | `irm https://raw.githubusercontent.com/AdishAssain/council-gate/main/install.ps1 \| iex` |
| **Claude Code** | `/plugin marketplace add github:AdishAssain/council-gate` then `/plugin install council-gate` |
| **Docker** (no install) | `docker run --rm -v "$PWD:/work" -w /work -e OPENROUTER_API_KEY=... ghcr.io/adishassain/council-gate review proposal.docx` |

The non-pip installers handle everything for you: install `uv`, install Python, install `council-gate` from PyPI, fix your PATH. **No prerequisite knowledge required, no Python pre-installed needed.**

Then:

```bash
council-gate init                                  # paste your OpenRouter key (free at https://openrouter.ai/keys)
council-gate review path/to/proposal.docx          # report saved to ./council-gate-proposal-<timestamp>.md
```

That's it. The default model mix runs on ~$1–2 of OpenRouter credit per review. Open the saved markdown in any viewer (Cursor, VS Code, GitHub, even Notes.app).

---

## What you can review

**Supported formats — auto-detected, no flags:**

- **Documents:** `.docx`, `.pdf`, `.pptx`, `.xlsx`, `.odt`, `.rtf`, `.epub` (converted to markdown via [MarkItDown](https://github.com/microsoft/markitdown))
- **Plain text & code:** `.md`, `.txt`, `.diff`, `.patch`, source code in any language — read verbatim

**Review styles** are auto-picked: `.docx`/`.pdf`/`.odt` → `proposal`; diffs / code / `.md` → `eng`. Override with `--mode`:

| `--mode` | Best for | Looks for |
|---|---|---|
| `eng` | engineering specs, PR diffs, design docs | correctness, edge cases, failure modes, security boundaries, silent-failure paths |
| `proposal` | grant proposals, strategy docs, pitches | claim/evidence asymmetry, vague language, audience fit, missing failure modes |
| `analysis` | data analyses, research findings | sample bias, confounders, unsupported causal claims, reproducibility |
| `general` | mixed / fallback | factual errors, internal inconsistencies, unsupported claims |

Custom prompt? `--prompt path/to/my-prompt.md`.

---

## What a report looks like

`council-gate review proposal.docx` saves a single markdown file. Excerpt:

```markdown
# Council review — `proposal.docx`

**The council disagreed.** Reviewers did not converge on a single set of findings.
Read the individual reviews below before acting.

## At a glance
| | |
|---|---|
| Verdict | ESCALATE |
| Reviewers | 4 returned reviews · 1 errored |
| Disagreement | 0.62 on a 0–1 scale (threshold 0.35; higher = more divergence) |
| Mode | proposal |

## What each reviewer said

### claude-haiku-4-5
| Severity | Where | Issue |
|---|---|---|
| MAJOR | Section 2 | Causal claim ("X drives Y") not supported by cited data |
| MINOR | Abstract | "Significantly improves" is unquantified |
…
```

Three verdicts:

- **`ESCALATE`** — reviewers disagreed; needs human judgement.
- **`CONSENSUS_CHECK`** — reviewers agreed, *but* the report ships with a checklist of dimensions where frontier AI models tend to share blindspots. Don't trust agreement as approval.
- **`INCONCLUSIVE`** — too few reviewers returned usable output (network, quota, etc).

---

## Other commands

| Command | What it does |
|---|---|
| `council-gate init` | Writes `~/.config/council-gate/.env` with your OpenRouter key. Interactive. Repairs your PATH if needed. |
| `council-gate review <file>` | Runs the council. Auto-saves a markdown report. `--no-save` for stdout-only; `--print` for both. |
| `council-gate doctor` | Diagnoses common setup issues: config present, key set, PATH on, codex CLI available. |
| `council-gate update` | Reinstalls the latest from PyPI. |

---

## How it works

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

The two original primitives are the **council** (cross-model, not cross-prompt) and the **entropy gate** (asymmetric — only *high* disagreement is a clean signal; *low* disagreement is treated as suspect, not as approval).

### Why cross-model, not cross-prompt

Same-model self-evaluation is biased. [Panickssery et al. (2024)](https://arxiv.org/abs/2404.13076) showed that LLM evaluators recognise and favour their own generations — the bias is consistent and measurable. A "council" of three Claude personas reviewing Claude-generated code is doing performance, not adversarial work.

`council-gate` enforces this with one rule: **the generator is excluded from the council.** Host integrations declare which provider produced the artifact via `COUNCIL_GENERATOR_PROVIDER`, and that provider's seats are dropped before the council runs.

### Why the gate is asymmetric

The naive design — *low entropy means trust, high entropy means escalate* — is half wrong.

[Kim et al. (2025)](https://arxiv.org/abs/2506.07962) studied 350+ LLMs and found that models agree roughly **60% of the time when both err**. The reported inter-model error correlation of r ≈ 0.77 implies an effective ensemble size of ~1.3 from three models — barely more diversified than asking one. The drivers: shared providers, shared architectures, and shared capability tier. Larger frontier models are *more* correlated even across providers, not less, because they converge on similar training distributions.

[Shin et al. (2025)](https://arxiv.org/abs/2502.17086) sharpened this: frontier LLMs systematically over-weight technical validity and under-weight novelty when reviewing scientific work. A shared blindspot, not random noise.

The gate handles this asymmetrically:

| Council output | Naive read | `council-gate` read |
|---|---|---|
| High disagreement | "Bad — humans must adjudicate." | Correct. Format the escalation. |
| Low disagreement | "Good — auto-proceed." | Treat as *suspect consensus*. Surface known correlated-failure dimensions explicitly. |

In practice, low-disagreement output ships with a checklist (`novelty`, `edge cases`, `failure modes`, `missing-data handling`, `long-term maintenance`) for the human to verify against, rather than a green check.

---

## Configuration

Lives at `~/.config/council-gate/.env` (XDG-compliant). `council-gate` never reads from the working directory; nothing lands in your repo.

Three keys matter:

- `COUNCIL_MODELS` — comma-separated OpenRouter model ids. Default is **cost-conscious** (Haiku, GPT-mini, Gemini Flash, Llama, Qwen, DeepSeek) — works on a $1–2 OpenRouter balance. Swap in flagship variants for higher-stakes reviews; see commented alternatives in `.env`.
- `COUNCIL_GENERATOR_PROVIDER` — slug (`anthropic`, `openai`, `google`) of whichever model produced the artifact. The corresponding seats are excluded from the council.
- `GATE_THRESHOLD` — disagreement threshold τ ∈ [0, 1] above which the gate fires escalation. Default `0.35`.

For an extra council seat using OpenAI's Codex CLI, install and authenticate `codex` separately ([openai/codex](https://github.com/openai/codex)).

---

## Privacy & secret-leak guardrails

`council-gate` sends the artifact body to LLM APIs of every council seat. Three layers of protection ship by default:

1. **Filename refusal.** The CLI refuses to read files matching obvious secret-bearing patterns (`.env`, `.pem`, `.key`, `id_rsa`, `*credentials*`, `*secret*`, `*.gpg`, `*.kdbx`).
2. **Inline redaction.** The artifact body is scanned for known secret patterns (OpenAI/Anthropic/Google/AWS/Slack/GitHub keys, JWTs, PEM private-key blocks) and redacted with `[REDACTED:…]` placeholders before any model sees it. Redaction count is logged.
3. **Disclosure (this section).** Don't pass files containing secrets, PII, or confidential third-party data. The redaction layer is defence in depth, not a substitute for judgement.

To bypass both, pass `--skip-redaction-check`. Don't use this flag unless you've audited the artifact yourself.

---

## Integrations

`council-gate` is a CLI; host integrations are thin wrappers that set `COUNCIL_GENERATOR_PROVIDER` before invoking it.

- **Claude Code plugin** — `.claude-plugin/` (use `/plugin install council-gate`)
- **Claude Code skill** — `integrations/claude-code/`
- **Codex CLI** — `integrations/codex/`
- **GitHub Action** — `integrations/github-action/`

Each is a copy-paste install. None require modifying `council-gate` itself.

---

## Contributing

PRs, issues, and dogfood reports all welcome. The most useful contribution is **running `council-gate` on your real proposals/PRs/specs and filing the friction.**

See [CONTRIBUTING.md](CONTRIBUTING.md) for dev setup, where help is most needed, and the project's two non-negotiable design primitives.

---

## Related work

- Panickssery, A., Bowman, S. R., & Feng, S. (2024). *LLM Evaluators Recognize and Favor Their Own Generations.* NeurIPS 2024. [arXiv:2404.13076](https://arxiv.org/abs/2404.13076)
- Kim, E., Garg, A., Peng, K., & Garg, N. (2025). *Correlated Errors in Large Language Models.* ICML 2025. [arXiv:2506.07962](https://arxiv.org/abs/2506.07962)
- Shin, H. et al. (2025). *Mind the Blind Spots: A Focus-Level Evaluation Framework for LLM Reviews.* EMNLP 2025 (Oral). [arXiv:2502.17086](https://arxiv.org/abs/2502.17086)

## How disagreement is measured

Pairwise Jaccard distance over normalized token sets extracted from each reviewer's findings, averaged across reviewer pairs. The metric measures lexical overlap, not semantic agreement — sufficient for the asymmetric gate's purpose, since high disagreement still means high disagreement, and low disagreement is *already* treated as suspect rather than as approval.

## License

MIT. See [LICENSE](LICENSE).
