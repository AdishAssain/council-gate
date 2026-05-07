# Changelog

## Stability

> **`council-gate` is pre-stable.** While the major version is `1.x` for ergonomics (the tool is functionally complete and shipping real reviews), the API surface — CLI flags, env var names, and report format — is **not frozen** until `2.0`. Minor versions may break things. Pin a version in CI / scripts.
>
> Until 2.0, treat version bumps as 0Ver-style: any release can change behaviour. Read the entry below before upgrading.

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
