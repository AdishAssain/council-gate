# Changelog

## Stability

> **`council-gate` is pre-stable.** While the major version is `1.x` for ergonomics (the tool is functionally complete and shipping real reviews), the API surface — CLI flags, env var names, and report format — is **not frozen** until `2.0`. Minor versions may break things. Pin a version in CI / scripts.
>
> Until 2.0, treat version bumps as 0Ver-style: any release can change behaviour. Read the entry below before upgrading.

## 1.4.0 — 2026-07-22

The learned-gate release. **Breaking** (pre-2.0 policy): the `v1`/`v2` entropy gates, `--gate-version`, `COUNCIL_GATE_VERSION`, and the `gate-v2` extra are removed.

**Verdicts come from a learned classifier now.** Fresh evaluation on 140 new councils showed the calibrated review form carries the whole signal: a 14-feature logistic regression over the form (seat count, severity/disposition mix, recommendation split) outperformed every entropy/clustering configuration; the strongest tabular foundation model could not beat the same features, students distilled from a TabPFN v2 teacher scored slightly higher than the direct fit, and a frontier LLM judge scored far below all of them. Three models ship as JSON assets with pure-Python inference (no new dependencies, microsecond verdicts):

- `lr` (default) — logistic regression fit directly on source-derived labels. Verdict reasons cite the top contributing factors.
- `tabpfn-lr`, `tabpfn-gb` — TabPFN-Lite models distilled from a TabPFN v2 teacher (Prior Labs License v1.1; license copy bundled). Scored slightly higher in evaluation; pick via `--gate` / `COUNCIL_GATE`.

Select with `--gate {lr,tabpfn-lr,tabpfn-gb}`; `GATE_THRESHOLD` now means escalation probability (default 0.5). Reports show an "Escalation score" instead of "Disagreement". Over-escalation on held-out data dropped from ~100% (old v1 default) / ~21% (old v2) to 8–12%.

**Removed:** `EntropyGate`, `EntropyGateV2`, semantic clustering, the MiniLM embedder, and the `gate-v2` extra (~600 lines). The block-vs-accept escalation rule and the structured-form pipeline that make the learned gate possible are unchanged from 1.3.0.

**Robustness:** structured-output requests that return empty content now fall back to plain prompting; malformed gateway responses retry instead of erroring; default seat timeout raised to 240 s for large artifacts.

## 1.3.0 — 2026-07-21

The structured-review release. Additive and backward-compatible; reports gain columns, no flags change meaning.

**Calibrated review form.** All four review modes now share one form: anchored severity definitions with a "pick the lower level" tie-break (severity is calibrated across reviewers, not self-scaled), a per-finding `disposition` (`defect`/`risk`/`gap`/`question`/`endorse`) and `confidence` (`low`/`med`/`high`), one atomic claim per finding, and a per-reviewer artifact-level `overall` verdict (`block`/`revise`/`accept`). Fields are ordered so models quote the artifact before claiming and justify before judging. Reports render the new columns plus each reviewer's overall stance.

**Gate reads overall verdicts.** If one reviewer would block what another would accept, the gate escalates — regardless of how similar their findings look. This catches disagreement that finding-overlap metrics are structurally blind to. Recommendations are recorded on every verdict.

**Optional gate v2** (`pip install 'council-gate[gate-v2]'`, `COUNCIL_GATE_VERSION=v2`): severity-weighted entropy over semantically clustered findings — same-issue-different-words counts as agreement; nit disagreements weigh less than critical ones. The default gate remains v1; the extra is a ~500 MB local model download, hence opt-in.

**Provider-side structured outputs.** Seats that support OpenRouter's `json_schema` response format get the form enforced server-side (`strict`, `require_parameters`); seats that don't, fall back to prompt-guided JSON automatically. `COUNCIL_STRUCTURED_OUTPUT=0` disables. Lenient parsing is retained as the universal validator either way, and now survives fenced blocks with any language tag, braces inside JSON strings, prose-wrapped payloads, uppercase enum values, and models that return `content: null`.

**Robustness.** A missing `gate-v2` extra now fails before the council spends API money, not after; unknown `COUNCIL_GATE_VERSION` values error instead of silently running v1; model-controlled text is escaped in report markdown; `--save-raw` dumps include the overall verdict.

**Refreshed default council** (`env.example`): six model families — GPT-5.6, Gemini 3.5, Claude Sonnet 5, GLM-5.2, DeepSeek V4, Kimi K3 — replacing the retired Llama seat and superseded Qwen 2.5.

Test suite: 50 → 132 tests; `mypy --strict` clean.

## 1.2.4 — 2026-05-07

Docs only — no PyPI republish (wheel is identical to 1.2.3).

- README: replace the broken `/plugin install council-gate` install path with a manual SKILL.md drop into `~/.claude/skills/council-gate/`. The slash-command path is blocked by an upstream Claude Code bug ([anthropics/claude-code#41653](https://github.com/anthropics/claude-code/issues/41653)) — the remote marketplace backend rejects every third-party plugin source regardless of `marketplace.json` shape. The manual skill drop activates on phrases like "review this proposal" and works on every Claude Code version.
- README: lead the install matrix with `uvx council-gate` — the only zero-install, zero-PATH-fix, zero-marketplace-bug path that works today.
- `.claude-plugin/marketplace.json`: defensive shape alignment with the format used by working Anthropic-channel plugins (`source: "./"` instead of `"."`, added `author` field on the plugin entry). Almost certainly not the cause of the upstream bug, but matches the working pattern so the plugin install lights up correctly once #41653 ships.

## 1.2.3 — 2026-05-06

PATCH: post-PyPI-publish cleanup. No behaviour change — same binary, faster install.

- Now that `1.2.2` is on PyPI, all installers point to PyPI instead of `git+https://...`:
  - `install.sh`, `install.ps1`: `uv tool install council-gate` (was `uv tool install git+https://...`).
  - Claude Code plugin (`commands/review.md`, `skills/council-gate/SKILL.md`): `uvx council-gate` (was `uvx --from git+...`). First-run plugin invocation goes from ~30 s git-clone to ~2 s pip-resolve.
  - README "Manual install" snippet: bare `uv tool install council-gate`.
- Plugin format fix: skill moved from flat `skills/council-gate.md` to `skills/council-gate/SKILL.md` per Claude Code plugin spec (skills must be `<name>/SKILL.md`, not flat).
- New `CONTRIBUTING.md` covering dev setup, the two non-negotiable design primitives, commit conventions, and where help is most useful.
- README rewritten for both engineer and non-engineer audiences: lead with two-audience framing, install matrix, "What a report looks like" excerpt, then the existing technical content (architecture, cross-model rationale, asymmetric-gate rationale, privacy guardrails) preserved beneath.

## 1.2.2 — 2026-05-06

PyPI-readiness housekeeping. No user-visible behavior change.

- `pyproject.toml`: added `[project.authors]`, fixed `Operating System :: POSIX` → `OS Independent` (we ship Windows + Docker), added `Documentation` and `Changelog` to `[project.urls]`, added `Programming Language :: Python :: 3.13` classifier, bumped `Development Status :: 3 - Alpha` → `4 - Beta`.
- `.github/workflows/release.yml`: PyPI publishing on `v*` tag via Trusted Publishing (OIDC, no API tokens). Also attaches wheels to a GitHub Release.
- Verified: `uv build` produces clean sdist + wheel, `twine check` passes, wheel installs in a fresh venv with the entrypoint resolving.

## 1.2.1 — 2026-05-06

- One-line installer for macOS/Linux/WSL (`install.sh`) and Windows (`install.ps1`). Both auto-install `uv`, install `council-gate`, and update your shell PATH so the binary works in fresh terminals — fixes the "command not found after restart" friction.
- Docker image published to `ghcr.io/adishassain/council-gate:latest` (and per-version tags). Hermetic, no Python required on host, ideal for CI.
- `council-gate update` now also runs `uv tool update-shell` so existing users get the PATH fix on next upgrade.

## 1.2.0 — 2026-05-06

- Multi-format ingestion: `.docx`, `.pdf`, `.pptx`, `.xlsx`, `.odt`, `.rtf`, `.epub` are now first-class inputs alongside `.md`/`.diff`/source code. Office formats are converted via [MarkItDown](https://github.com/microsoft/markitdown) before review.
- Smart `--mode` default: `.docx`/`.pdf`/`.odt` artifacts default to `proposal` review; everything else stays on `eng`. Override with `--mode` as before.
- Friendly errors throughout: file-load failures, missing dependencies, and unexpected crashes now print plain-English messages instead of Python tracebacks. `--verbose` re-enables full tracebacks.
- More resilient PATH setup: `council-gate init` now writes to both `.zshrc`+`.zprofile` (zsh) and `.bashrc`+`.bash_profile` (bash), so the binary survives a terminal restart on macOS where Terminal.app launches login shells.
- `council-gate doctor` now reports the resolved `council-gate` binary path.
- Helpful messages for unsupported Apple iWork formats (`.pages`, `.numbers`, `.keynote`, `.gdoc`) telling the user how to export.

## 1.1.0

- README review-modes table; version bump.

## 1.0.0

- Initial public release.
