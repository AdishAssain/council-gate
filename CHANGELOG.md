# Changelog

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
