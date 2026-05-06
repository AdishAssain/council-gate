"""Council seat providers.

Two implementations today: a subprocess wrapper around the OpenAI Codex CLI,
and an HTTP client against OpenRouter (which fans out to any model in their
catalog under one API key). They share a duck-typed shape: an instance has
`model_id`, `provider`, and a `review(artifact, system_prompt) -> Review`
method. No ABC; the Council orchestrator only cares about the call shape.
"""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol

import httpx

from council_gate.parsing import parse_findings
from council_gate.types import Review


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
        return Review(
            model_id=self.model_id,
            provider=self.provider,
            findings=parse_findings(raw),
            raw_text=raw,
        )


class OpenRouterProvider:
    """Routes to any model on OpenRouter via a single API key."""

    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, model_id: str, timeout_s: float = 120.0) -> None:
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
        payload = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": artifact},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "X-Title": "council-gate",
        }
        resp = httpx.post(self.BASE_URL, headers=headers, json=payload, timeout=self._timeout)
        if resp.status_code >= 400:
            # Friendly error mapping; the council surfaces this on Review.error.
            short = self._friendly_http_error(resp)
            raise RuntimeError(f"{self.model_id}: {short}")
        body = resp.json()
        # OpenRouter sometimes returns 200 with {"error": ...} (rate limit,
        # model unavailable, content filter). Detect those before assuming
        # the OpenAI-shape choices[] is present.
        if "error" in body and "choices" not in body:
            err = body["error"]
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            raise RuntimeError(f"openrouter returned 200 with error: {msg[:300]}")
        try:
            raw = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(
                f"openrouter response missing choices[0].message.content: {body!r}"[:500]
            ) from e
        return Review(
            model_id=self.model_id,
            provider=self.provider,
            findings=parse_findings(raw),
            raw_text=raw,
        )

    @staticmethod
    def _friendly_http_error(resp: httpx.Response) -> str:
        code = resp.status_code
        canonical = {
            401: "401 Unauthorized — OPENROUTER_API_KEY rejected. Re-check the key at https://openrouter.ai/keys.",
            402: "402 Payment Required — likely insufficient OpenRouter balance for this model. Top up or drop the model from COUNCIL_MODELS.",
            403: "403 Forbidden — your account may not have access to this model.",
            404: "404 Not Found — model id misspelled? Check https://openrouter.ai/models.",
            429: "429 Rate Limited — back off, or pick less popular models.",
            500: "500 Server Error from OpenRouter.",
            502: "502 Bad Gateway from OpenRouter.",
            503: "503 Service Unavailable — OpenRouter or upstream provider is down.",
        }
        if code in canonical:
            return canonical[code]
        try:
            body = resp.json()
            msg = body.get("error", {}).get("message", "")
        except Exception:
            msg = ""
        return f"HTTP {code}{f' — {msg}' if msg else ''}"
