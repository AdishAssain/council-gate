"""Council seat providers.

Two implementations today: a subprocess wrapper around the OpenAI Codex CLI,
and an HTTP client against OpenRouter (which fans out to any model in their
catalog under one API key). They share a duck-typed shape: an instance has
`model_id`, `provider`, and a `review(artifact, system_prompt) -> Review`
method. No ABC; the Council orchestrator only cares about the call shape.
"""
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Protocol

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from council_gate.parsing import parse_review
from council_gate.types import Review, review_json_schema

log = logging.getLogger(__name__)

# Frontier models write verbose rationales even on tiny artifacts, so the
# floor is sized for typical review output (~15-30 findings with rationale +
# evidence) rather than scaled to input size. Ceiling keeps runaways from
# silently burning credits.
_MAX_TOKENS_FLOOR = 8000
_MAX_TOKENS_CEIL = 16000


def _max_tokens_for(artifact: str) -> int:
    override = os.environ.get("COUNCIL_MAX_TOKENS")
    if override:
        try:
            return max(500, int(override))
        except ValueError:
            log.warning("COUNCIL_MAX_TOKENS=%r is not an int, ignoring", override)
    return min(_MAX_TOKENS_CEIL, max(_MAX_TOKENS_FLOOR, len(artifact) // 4))


class _RetryableHTTPError(RuntimeError):
    """Marker for transient HTTP failures tenacity should retry.

    Auth/quota/permanent errors raise plain RuntimeError and skip retry.
    Subclasses RuntimeError so callers (and tests) catching RuntimeError
    still see the final exhausted-retries failure.
    """


class _SchemaUnsupported(RuntimeError):
    """The provider rejected a structured-output request."""


def _is_retryable_status(code: int) -> bool:
    return code == 429 or 500 <= code < 600


_RETRYABLE_HTTPX_ERRORS = (
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.RemoteProtocolError,
)


class Provider(Protocol):
    model_id: str
    provider: str

    def review(self, artifact: str, system_prompt: str) -> Review: ...


class CodexProvider:
    """Calls the OpenAI Codex CLI in read-only exec mode.

    Hermetic by default: codex runs inside a fresh temp directory containing
    only the artifact, so it cannot read surrounding files in the user's cwd.
    Pass repo_root explicitly to opt back into wider filesystem context (e.g.
    when reviewing a real PR diff and codex needs to read referenced files).

    Codex must be installed and authenticated separately:
    https://github.com/openai/codex
    """

    model_id = "openai/codex-cli"
    provider = "openai"

    def __init__(self, repo_root: Path | None = None, timeout_s: int = 300) -> None:
        if shutil.which("codex") is None:
            raise RuntimeError("codex CLI not found on PATH")
        # repo_root=None → hermetic tempdir per call. Explicit value → that dir.
        self.repo_root = repo_root
        self._timeout = timeout_s

    def review(self, artifact: str, system_prompt: str) -> Review:
        prompt = f"{system_prompt}\n\nARTIFACT:\n{artifact}"
        if self.repo_root is None:
            with tempfile.TemporaryDirectory(prefix="council-gate-codex-") as td:
                return self._exec(prompt, Path(td))
        return self._exec(prompt, self.repo_root)

    @retry(
        retry=retry_if_exception_type(subprocess.TimeoutExpired),
        wait=wait_exponential_jitter(initial=1.0, max=10.0),
        stop=stop_after_attempt(2),
        reraise=True,
    )
    def _exec(self, prompt: str, root: Path) -> Review:
        result = subprocess.run(
            [
                "codex", "exec", prompt,
                "-C", str(root),
                "-s", "read-only",
                "--skip-git-repo-check",  # required when running in a tempdir
                "-c", 'model_reasoning_effort="high"',
            ],
            capture_output=True,
            text=True,
            timeout=self._timeout,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "")[:500]
            raise RuntimeError(
                f"codex exited {result.returncode}: {err.strip()}"
            )
        raw = result.stdout
        findings, overall = parse_review(raw)
        return Review(
            model_id=self.model_id,
            provider=self.provider,
            findings=findings,
            raw_text=raw,
            overall=overall,
        )


class OpenRouterProvider:
    """Routes to any model on OpenRouter via a single API key."""

    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, model_id: str, timeout_s: float = 240.0) -> None:
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY not set")
        if "/" not in model_id:
            raise ValueError(f"model_id must be 'provider/model', got {model_id!r}")
        self.model_id = model_id
        self.provider = model_id.split("/", 1)[0]
        self._api_key = api_key
        self._timeout = timeout_s

    def review(self, artifact: str, system_prompt: str) -> Review:
        max_tok = _max_tokens_for(artifact)
        payload = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": artifact},
            ],
            "max_tokens": max_tok,
        }
        if os.environ.get("COUNCIL_STRUCTURED_OUTPUT", "1") == "1":
            structured = payload | {
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "review_form",
                        "strict": True,
                        "schema": review_json_schema(),
                    },
                },
                # Route only to providers that honor response_format; without
                # this a provider may silently drop it.
                "provider": {"require_parameters": True},
            }
            try:
                raw = self._complete(structured, max_tok, schema=True)
            except _SchemaUnsupported:
                raw = self._complete(payload, max_tok)
        else:
            raw = self._complete(payload, max_tok)
        findings, overall = parse_review(raw)
        return Review(
            model_id=self.model_id,
            provider=self.provider,
            findings=findings,
            raw_text=raw,
            overall=overall,
        )

    @retry(
        retry=retry_if_exception_type((_RetryableHTTPError, *_RETRYABLE_HTTPX_ERRORS)),
        wait=wait_exponential_jitter(initial=0.5, max=8.0),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _complete(self, payload: dict[str, Any], max_tok: int, schema: bool = False) -> str:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "X-Title": "council-gate",
        }
        resp = httpx.post(self.BASE_URL, headers=headers, json=payload, timeout=self._timeout)
        if resp.status_code >= 400:
            # Friendly error mapping; the council surfaces this on Review.error.
            short = self._friendly_http_error(resp)
            if _is_retryable_status(resp.status_code):
                # Tenacity catches this and retries; non-retryable errors
                # raise plain RuntimeError below and fail fast.
                raise _RetryableHTTPError(f"{self.model_id}: {short}")
            if schema and resp.status_code in (400, 404, 422):
                # Model/provider rejected the schema request; caller retries
                # without it. Auth/quota errors above fail fast either way.
                raise _SchemaUnsupported(f"{self.model_id}: {short}")
            raise RuntimeError(f"{self.model_id}: {short}")
        try:
            body = resp.json()
        except ValueError as e:
            # Truncated/malformed body from the gateway — transient, retry.
            raise _RetryableHTTPError(
                f"{self.model_id}: malformed response body from openrouter"
            ) from e
        # OpenRouter sometimes returns 200 with {"error": ...} (rate limit,
        # model unavailable, content filter). Detect those before assuming
        # the OpenAI-shape choices[] is present.
        if "error" in body and "choices" not in body:
            err = body["error"]
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            raise RuntimeError(f"openrouter returned 200 with error: {msg[:300]}")
        try:
            choice = body["choices"][0]
            raw = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(
                f"openrouter response missing choices[0].message.content: {body!r}"[:500]
            ) from e
        if not isinstance(raw, str) or not raw.strip():
            if schema:
                # Constrained decoding produced nothing; worth one plain retry.
                raise _SchemaUnsupported(f"{self.model_id}: empty structured response")
            # Some models return content: null (reasoning-only or filtered).
            raise RuntimeError(f"{self.model_id}: model returned empty content")
        finish = choice.get("finish_reason", "")
        if finish == "length":
            # Hit max_tokens. JSON output is almost certainly truncated and the
            # parser will fail; surface this in the report rather than silently
            # dropping findings.
            log.warning(
                "%s: response truncated at max_tokens=%d — raise via COUNCIL_MAX_TOKENS",
                self.model_id,
                max_tok,
            )
            raw = f"[TRUNCATED at max_tokens={max_tok}]\n{raw}"
        return raw

    @staticmethod
    def _friendly_http_error(resp: httpx.Response) -> str:
        code = resp.status_code
        canonical = {
            401: "Sign-in failed. Check your OpenRouter key: https://openrouter.ai/keys",
            402: "Low OpenRouter balance for this model. Top up or skip it: https://openrouter.ai/credits",
            403: "This model isn't on your OpenRouter plan.",
            404: "Model id not found: https://openrouter.ai/models",
            429: "Rate limited. Try again shortly.",
            500: "OpenRouter hiccup. Usually clears in a minute.",
            502: "OpenRouter hiccup. Usually clears in a minute.",
            503: "OpenRouter briefly unavailable.",
        }
        if code in canonical:
            return canonical[code]
        try:
            body = resp.json()
            msg = body.get("error", {}).get("message", "")
        except Exception:
            msg = ""
        return f"HTTP {code}{f' — {msg}' if msg else ''}"
