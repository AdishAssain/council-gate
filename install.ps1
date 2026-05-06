# council-gate one-line installer for Windows PowerShell.
# Usage:
#   irm https://raw.githubusercontent.com/AdishAssain/council-gate/main/install.ps1 | iex
#
# - Installs uv if missing (Astral's official installer)
# - Installs council-gate via `uv tool install`
# - Runs `uv tool update-shell` so the binary is on PATH in new shells
# - Adds the uv tool bin dir to PATH for the *current* shell

$ErrorActionPreference = "Stop"

$Package = "council-gate"

function Say($msg)  { Write-Host "==> $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "[ok] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Warning $msg }

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Say "uv not found. Installing uv first..."
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    # Refresh PATH for this session so we can call uv immediately
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","User") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path","Machine")
    Ok "uv installed"
} else {
    Ok "uv already installed: $((Get-Command uv).Source)"
}

Say "Installing $Package from PyPI"
uv tool install --force $Package
Ok "council-gate installed"

Say "Updating shell config so council-gate is on PATH in new sessions"
try { uv tool update-shell } catch { Warn "uv tool update-shell did not modify PATH (may already be set)" }

# Refresh PATH for *this* session
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","User") + ";" +
            [System.Environment]::GetEnvironmentVariable("Path","Machine")

Write-Host ""
Ok "council-gate is ready"
Write-Host @"

Next:
  1. council-gate init                          # one-time: paste your OpenRouter key
  2. council-gate review path\to\proposal.docx  # review a doc

If 'council-gate' isn't found in a new PowerShell window, close and reopen it
(Windows needs the new PATH to propagate), then run:
  council-gate doctor

"@
