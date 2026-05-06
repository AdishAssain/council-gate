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
