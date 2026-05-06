# Contributing to council-gate

Thanks for considering it. This is a small project with a sharp scope, so a few notes up front will save us both time.

## What contribution actually helps

Ranked by usefulness:

1. **Dogfood reports.** Run `council-gate review` on a real proposal, PR, or doc and file what broke or felt wrong. This is where almost every meaningful improvement has come from.
2. **Bug reports** with the saved markdown report attached (`./council-gate-<file>-<timestamp>.md`).
3. **PRs** that close a TODO line or fix a real issue. See [areas where help is most useful](#where-help-is-most-useful).
4. **Documentation** — examples, walkthroughs, integration recipes for tools we don't yet support.
5. **Translations of error messages and prompts** — the friendly-error-message work is meant for non-engineers; if you find one that confused someone, replace it.

## Two design primitives — non-negotiable

`council-gate` is built on two ideas. PRs that violate them will be declined no matter how clean the code:

1. **Cross-model, not cross-prompt.** Three Claudes reviewing Claude output is not adversarial. The council MUST exclude the generator's provider. Don't add a feature that lets the generator review its own output.
2. **The entropy gate is asymmetric.** *High* disagreement is the clean signal. *Low* disagreement is **suspect consensus**, not approval — frontier LLMs share blindspots. Don't add a "green check" path that treats agreement as approval.

If you have an idea that conflicts with either, open an issue first to discuss the tradeoff.

## Dev setup

Requires Python ≥ 3.12 and [`uv`](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/AdishAssain/council-gate.git
cd council-gate
uv sync --extra dev
uv run pre-commit install      # runs ruff + pytest before each commit
uv run pytest                  # 50+ tests, ~1s
```

Run a real review against the repo's own README to sanity-check your env:

```bash
cp ~/.config/council-gate/.env .env.local 2>/dev/null  # if you already have a key
uv run council-gate review README.md --no-save --print
```

## Making changes

- **Branch off `main`.** No long-lived feature branches.
- **Tests must pass.** `uv run pytest`. New features need new tests; bugfixes need a regression test.
- **Lint must pass.** `uv run ruff check . && uv run mypy src/`. Pre-commit catches most issues locally.
- **One logical change per PR.** Drive-by refactors that aren't required for the change → separate PR.
- **Keep diffs small.** A 50-line PR gets reviewed today. A 500-line PR doesn't.

### Commit messages

Loosely follow [Conventional Commits](https://www.conventionalcommits.org/) — the type prefix matters more than the format:

```
feat: add JSON output mode for CI consumption
fix: handle 402 mid-run by dropping the failing seat and retrying
docs: clarify mode selection in README
ci: add TestPyPI dry-run workflow
```

Use `feat:` for MINOR-bumping changes, `fix:` / `docs:` / `chore:` / `ci:` / `refactor:` for PATCH-level. See the [versioning policy](CHANGELOG.md#versioning-policy) for what triggers MAJOR/MINOR/PATCH.

### Versioning

We're pre-stable: `1.x` is functionally complete but the API surface (CLI flags, env vars, report format) isn't frozen until `2.0`. Treat minor versions as freely break-able for now. Pin `council-gate==X.Y.Z` in CI / scripts.

For maintainers: every release is a tag like `v1.2.3` pushed to `main`. The `release.yml` workflow builds, OIDC-publishes to PyPI, and cuts a GitHub Release automatically.

## Where help is most useful

Drawn from the live TODO list:

- **Embedding-based disagreement metric** — current Jaccard-on-tokens is a placeholder. Cross-model semantic similarity would catch paraphrased disagreement.
- **JSON output mode** — `--output json` for CI / connector consumption (precondition for Slack/Linear integrations).
- **Auto-degrade** — if a model 402s mid-run, drop it and retry the rest without it.
- **Directory / glob input** — `council-gate review ./specs/` so a "test directory" is reviewable in one call.
- **Per-mode threshold profiles** — PR diffs vs strategy docs want different τ.
- **Anthropic-direct adapter** — currently we route via OpenRouter; a direct adapter would give a fallback path.
- **MCP server** — a daemon mode exposing `council_review(path) → markdown` as a tool, for richer Claude Code integration.
- **More host integrations** — Cursor, Continue, Aider, etc. Look at `integrations/` for the pattern.

If you'd like to take any of these, comment on the relevant TODO line in an issue first so we don't double up.

## Reporting security issues

Please do **not** open a public GitHub issue for security bugs. Email the maintainer or use GitHub's private vulnerability reporting. See [SECURITY.md](SECURITY.md).

## Code of conduct

Be excellent to each other. The reviewer who took an hour out of their day for your PR has earned good faith; the contributor who shipped something has earned a real review, not a drive-by nit.

If a discussion gets heated, step away for an hour and come back.

## Licensing

By submitting a PR you agree to license your contribution under the project's [MIT License](LICENSE).
