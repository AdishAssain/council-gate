#!/usr/bin/env sh
# council-gate one-line installer.
# Usage:  curl -LsSf https://raw.githubusercontent.com/AdishAssain/council-gate/main/install.sh | sh
#
# - Installs uv if missing (Astral's official installer)
# - Installs council-gate via `uv tool install`
# - Runs `uv tool update-shell` so the binary is on PATH in new terminals
# - Adds ~/.local/bin to PATH for the *current* shell so the user can run
#   council-gate immediately without opening a new terminal

set -eu

REPO="git+https://github.com/AdishAssain/council-gate"
LOCAL_BIN="$HOME/.local/bin"

say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m✓\033[0m   %s\n' "$*"; }
warn() { printf '\033[1;33m!\033[0m   %s\n' "$*" >&2; }

if ! command -v uv >/dev/null 2>&1; then
  say "uv not found. Installing uv first…"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.cargo/bin:$LOCAL_BIN:$PATH"
  ok "uv installed"
else
  ok "uv already installed: $(command -v uv)"
fi

say "Installing council-gate from $REPO"
uv tool install --force "$REPO"
ok "council-gate installed to $LOCAL_BIN/council-gate"

# Ensure PATH is permanent in new shells (writes to .zshrc/.bashrc/.config/fish/...)
say "Updating shell config so council-gate is on PATH in new terminals"
uv tool update-shell || warn "uv tool update-shell did not modify any shell config (may already be set)"

# Make it work in *this* shell too, so the user can run council-gate immediately
case ":$PATH:" in
  *":$LOCAL_BIN:"*) ;;
  *) export PATH="$LOCAL_BIN:$PATH" ;;
esac

cat <<EOF

$(ok "council-gate $(council-gate --help >/dev/null 2>&1 && echo "is ready" || echo "installed")")

Next:
  1. council-gate init                          # one-time: paste your OpenRouter key
  2. council-gate review path/to/proposal.docx  # review a doc

If 'council-gate' isn't found in a new terminal, open a fresh tab and try again
(some shells need a restart to pick up the new PATH), or run:
  $LOCAL_BIN/council-gate doctor

EOF
