# Security policy

## What council-gate handles

`council-gate` reads a text artifact from disk and sends its body to N external LLM APIs (OpenRouter, OpenAI Codex CLI). The artifact body crosses the local trust boundary the moment a council seat dispatches.

Three layers of in-tree protection ship by default:

1. **Filename refusal** — see `REFUSED_NAME_PATTERNS` in `src/council_gate/redaction.py`. The CLI refuses to read files matching obvious secret-bearing patterns.
2. **Inline pattern redaction** — see `SECRET_PATTERNS` in the same module. The artifact body is scanned for known secret shapes before any model sees it.
3. **Disclosure** — `README.md` §"Privacy and secret-leak guardrails."

The redaction layer is conservative defence in depth. It is not, and is not intended to be, a substitute for the user's own judgement about what to feed the tool.

## Reporting a vulnerability

If you find:

- A redaction-pattern miss (a real-world secret that slips through `redact()`)
- A refused-filename gap (a known secret-bearing filename or path that the CLI does not refuse)
- A code path where the artifact body, an env-loaded API key, or any other sensitive value can leak to logs, stdout, an error message, or a model API in violation of the README's claims
- Any other bug with security implications

…please report it privately by opening a [security advisory](https://github.com/AdishAssain/council-gate/security/advisories/new). Do not file a public issue.

When reporting, include:

- A minimal reproducer (file content or command)
- The expected vs observed behaviour
- The version (commit SHA) you tested against

## Out of scope

- The user explicitly passing `--skip-redaction-check`. That flag's purpose is to bypass the layer; bypassing it is not a vulnerability.
- Secrets the user themselves typed into a prompt or piped into the CLI — `council-gate` cannot retroactively redact what the user pasted.
- Any third-party LLM provider's storage, retention, or training-data policies. Choose providers whose policies match your data sensitivity.

## Coordinated disclosure

We aim to acknowledge reports within 72 hours and patch verified issues within 14 days. After a fix lands, we'll credit the reporter (or keep them anonymous on request) in the relevant CHANGELOG entry.
