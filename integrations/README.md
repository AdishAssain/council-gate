# Host integrations

`council-gate` is a CLI; host integrations are thin wrappers that set `COUNCIL_GENERATOR_PROVIDER` (so the council excludes the generator's own provider) and shell out.

| Host | Path | Status |
|---|---|---|
| Claude Code | `claude-code/` | shipped |
| Codex CLI | `codex/` | shipped |
| GitHub Action | `github-action/` | scaffolded |
| Pre-push hook | — | v1.1 (pre-push, not pre-commit — see README) |

Each integration is a copy-paste install. None require modifying `council-gate` itself.

## Why per-host integrations matter

The asymmetric-gate design depends on excluding the generator's provider from the council. If you generate with Claude and the council includes Claude, the [Panickssery et al. (2024)](https://arxiv.org/abs/2404.13076) self-favouring bias contaminates the verdict. The host integration's only job is to set the right env var before invoking the CLI — it knows which model produced the artifact.
