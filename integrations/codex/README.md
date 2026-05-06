# Codex CLI integration

When OpenAI's [Codex CLI](https://github.com/openai/codex) is the artifact's author (i.e. you generated the spec / diff / plan inside a Codex session), council-gate must exclude OpenAI seats from the council. Otherwise OpenAI is reviewing OpenAI — exactly the self-favouring bias the asymmetric gate is designed to avoid ([Panickssery et al. 2024](https://arxiv.org/abs/2404.13076)).

## Prerequisites

```bash
uv tool install council-gate    # or: pip install council-gate
council-gate init                      # writes ~/.config/council-gate/.env
$EDITOR ~/.config/council-gate/.env    # set OPENROUTER_API_KEY
```

## One-off invocation

From any shell, on any artifact you generated with Codex:

```bash
COUNCIL_GENERATOR_PROVIDER=openai council-gate review path/to/artifact
```

This drops both:

- OpenRouter `openai/*` seats (e.g. `openai/gpt-5`)
- The local Codex CLI seat (`provider="openai"`)

…leaving Anthropic, Google, Meta, Qwen, and DeepSeek (per the default `COUNCIL_MODELS`).

## Shell alias (recommended)

Add to `~/.zshrc` or `~/.bashrc`:

```bash
alias cg-codex='COUNCIL_GENERATOR_PROVIDER=openai council-gate'
```

Then: `cg-codex review path/to/spec.md`.

## Codex config snippet

If you use Codex's project-level config to pre-set environment variables, add `COUNCIL_GENERATOR_PROVIDER=openai` there so any council-gate invocation from inside Codex sessions automatically excludes the right seats:

```toml
# ~/.codex/config.toml — add under your project's profile
[env]
COUNCIL_GENERATOR_PROVIDER = "openai"
```

(Verify the exact config path / shape against your installed Codex version — the env-var mechanism is the load-bearing piece, however it's set.)

## Why this matters specifically for Codex users

The independent code review that helped harden council-gate found that excluding `openai` drops *two* seats at once (gpt-5 + the Codex CLI itself). With six default seats, that still leaves five distinct providers — but if you've trimmed `COUNCIL_MODELS` to a smaller set, double-check your council still has ≥2 seats after exclusion, otherwise the CLI will refuse to run.
