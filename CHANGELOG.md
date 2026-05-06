# Changelog

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
