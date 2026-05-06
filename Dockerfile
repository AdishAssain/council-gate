# Hermetic council-gate image. ~150MB, no venv state, runs as non-root.
# Usage:
#   docker run --rm -v "$PWD:/work" -w /work \
#       -e OPENROUTER_API_KEY=sk-or-... \
#       ghcr.io/adishassain/council-gate review proposal.docx

FROM python:3.12-slim

# uv for the install — same toolchain as the host installer
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /opt/council-gate
COPY pyproject.toml README.md LICENSE ./
COPY src ./src

# System install (no venv) so the entrypoint resolves without activation
RUN uv pip install --system --no-cache .

# Non-root user — review jobs must not run as root inside the container
RUN useradd --create-home --shell /bin/bash council
USER council
WORKDIR /work

ENTRYPOINT ["council-gate"]
CMD ["--help"]
