# GitHub Action

Drop the workflow below into `.github/workflows/council-gate.yml` in your repo to run `council-gate` on PRs.

```yaml
name: council-gate
on:
  pull_request:
    paths:
      - "docs/specs/**"
      - "docs/proposals/**"
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: AdishAssain/council-gate/integrations/github-action@v1
        with:
          artifact-path: docs/specs/changed-spec.md
          mode: eng
          generator-provider: anthropic   # or openai, google — whichever produced the doc
          openrouter-api-key: ${{ secrets.OPENROUTER_API_KEY }}
```

The action installs `council-gate` from PyPI, sets the env vars, and runs `review`. Output goes to the workflow log; on `ESCALATE` verdict the formatted escalation message is in the log ready to paste into a PR comment or chat.

## Status: scaffolded

Action.yml ships in this repo but has not been published as a Marketplace action yet. Use the `uses: <local-path>@<sha>` form against this repo's commit hash until v1.1.
