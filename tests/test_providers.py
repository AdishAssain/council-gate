"""HTTP-mocked tests for OpenRouterProvider.

Covers the response-shape gaps the independent review flagged: 200-with-error
payloads (rate limit / model unavailable), missing choices array, etc.
"""

import json as _json

import httpx
import pytest

from council_gate.providers import OpenRouterProvider


def _set_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")


def _mock_post(monkeypatch, response_json: dict, status: int = 200):
    def fake_post(url, headers=None, json=None, timeout=None):
        return httpx.Response(
            status_code=status,
            content=_json.dumps(response_json).encode(),
            headers={"content-type": "application/json"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)


def test_openrouter_happy_path(monkeypatch):
    _set_key(monkeypatch)
    _mock_post(
        monkeypatch,
        {
            "choices": [
                {"message": {"content": "[CRITICAL] foo:1 — bug\n[MINOR] bar:2 — nit"}}
            ]
        },
    )
    p = OpenRouterProvider("anthropic/claude-test")
    review = p.review("artifact body", "system prompt")
    assert review.provider == "anthropic"
    assert review.model_id == "anthropic/claude-test"
    assert "bug" in review.raw_text
    assert len(review.findings) == 2


def test_openrouter_200_with_error_payload(monkeypatch):
    _set_key(monkeypatch)
    _mock_post(
        monkeypatch,
        {"error": {"message": "Rate limit exceeded for model X", "code": 429}},
    )
    p = OpenRouterProvider("openai/gpt-test")
    with pytest.raises(RuntimeError, match="openrouter returned 200 with error"):
        p.review("artifact", "prompt")


def test_openrouter_malformed_response(monkeypatch):
    _set_key(monkeypatch)
    _mock_post(monkeypatch, {"unexpected": "shape"})
    p = OpenRouterProvider("openai/gpt-test")
    with pytest.raises(RuntimeError, match="missing choices"):
        p.review("artifact", "prompt")


def test_openrouter_4xx_raises_with_friendly_message(monkeypatch):
    _set_key(monkeypatch)
    _mock_post(monkeypatch, {"error": "unauthorized"}, status=401)
    p = OpenRouterProvider("openai/gpt-test")
    with pytest.raises(RuntimeError, match="Sign-in failed"):
        p.review("artifact", "prompt")


def test_openrouter_402_friendly_message(monkeypatch):
    _set_key(monkeypatch)
    _mock_post(monkeypatch, {"error": "balance"}, status=402)
    p = OpenRouterProvider("openai/gpt-test")
    with pytest.raises(RuntimeError, match="Low OpenRouter balance"):
        p.review("artifact", "prompt")


def test_openrouter_requires_provider_prefix(monkeypatch):
    _set_key(monkeypatch)
    with pytest.raises(ValueError, match="provider/model"):
        OpenRouterProvider("just-a-model")


def test_openrouter_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        OpenRouterProvider("openai/gpt-test")


def test_openrouter_provider_inferred_from_model_id(monkeypatch):
    _set_key(monkeypatch)
    p = OpenRouterProvider("meta-llama/llama-3.3-70b-instruct")
    assert p.provider == "meta-llama"


def test_openrouter_sets_max_tokens_in_payload(monkeypatch):
    _set_key(monkeypatch)
    captured: dict = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return httpx.Response(
            status_code=200,
            content=_json.dumps(
                {"choices": [{"message": {"content": "[CRITICAL] x:1 — y"}}]}
            ).encode(),
            headers={"content-type": "application/json"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    p = OpenRouterProvider("openai/gpt-test")
    p.review("artifact body", "system prompt")
    assert "max_tokens" in captured["json"]
    assert captured["json"]["max_tokens"] >= 4000  # floor


def test_openrouter_max_tokens_override_via_env(monkeypatch):
    _set_key(monkeypatch)
    monkeypatch.setenv("COUNCIL_MAX_TOKENS", "8192")
    captured: dict = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return httpx.Response(
            status_code=200,
            content=_json.dumps(
                {"choices": [{"message": {"content": "ok"}}]}
            ).encode(),
            headers={"content-type": "application/json"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    p = OpenRouterProvider("openai/gpt-test")
    p.review("a", "b")
    assert captured["json"]["max_tokens"] == 8192


def test_openrouter_flags_truncated_output(monkeypatch):
    _set_key(monkeypatch)
    _mock_post(
        monkeypatch,
        {
            "choices": [
                {
                    "message": {"content": '{"findings": [{"severity": "crit'},
                    "finish_reason": "length",
                }
            ]
        },
    )
    p = OpenRouterProvider("openai/gpt-test")
    review = p.review("artifact", "prompt")
    assert "TRUNCATED" in review.raw_text


def _sequence_post(monkeypatch, responses: list[tuple[int, dict]]):
    """Mock httpx.post to return responses in order, raising IndexError if
    called more times than expected — that surfaces missing retries."""
    calls = {"n": 0}

    def fake_post(url, headers=None, json=None, timeout=None):
        status, body = responses[calls["n"]]
        calls["n"] += 1
        return httpx.Response(
            status_code=status,
            content=_json.dumps(body).encode(),
            headers={"content-type": "application/json"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    return calls


def test_openrouter_retries_on_429_then_succeeds(monkeypatch):
    _set_key(monkeypatch)
    success_body = {
        "choices": [{"message": {"content": "[CRITICAL] x:1 — y"}}]
    }
    calls = _sequence_post(
        monkeypatch,
        [
            (429, {"error": "rate limited"}),
            (200, success_body),
        ],
    )
    p = OpenRouterProvider("openai/gpt-test")
    review = p.review("artifact", "prompt")
    assert calls["n"] == 2
    assert "y" in review.raw_text


def test_openrouter_retries_on_503_then_succeeds(monkeypatch):
    _set_key(monkeypatch)
    success_body = {"choices": [{"message": {"content": "ok"}}]}
    calls = _sequence_post(
        monkeypatch,
        [
            (503, {"error": "service unavailable"}),
            (503, {"error": "still unavailable"}),
            (200, success_body),
        ],
    )
    p = OpenRouterProvider("openai/gpt-test")
    p.review("artifact", "prompt")
    assert calls["n"] == 3


def test_openrouter_gives_up_after_max_attempts(monkeypatch):
    _set_key(monkeypatch)
    calls = _sequence_post(
        monkeypatch,
        [(500, {"error": "boom"})] * 3,
    )
    p = OpenRouterProvider("openai/gpt-test")
    with pytest.raises(RuntimeError):
        p.review("artifact", "prompt")
    assert calls["n"] == 3  # 3 attempts, no more


def test_openrouter_does_not_retry_on_401(monkeypatch):
    _set_key(monkeypatch)
    calls = _sequence_post(monkeypatch, [(401, {"error": "unauthorized"})])
    p = OpenRouterProvider("openai/gpt-test")
    with pytest.raises(RuntimeError, match="Sign-in failed"):
        p.review("artifact", "prompt")
    assert calls["n"] == 1  # no retry on auth error
