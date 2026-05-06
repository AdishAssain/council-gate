import pytest

from council_gate.council import Council
from council_gate.types import Finding, Review


class FakeProvider:
    def __init__(self, model_id: str, provider: str, response: str = "ok"):
        self.model_id = model_id
        self.provider = provider
        self._response = response

    def review(self, artifact: str, system_prompt: str) -> Review:
        return Review(
            model_id=self.model_id,
            provider=self.provider,
            findings=[Finding(severity="major", summary=self._response)],
            raw_text=self._response,
        )


class FailingProvider:
    model_id = "broken/x"
    provider = "broken"

    def review(self, artifact: str, system_prompt: str) -> Review:
        raise RuntimeError("boom")


def test_council_dispatches_all_seats():
    seats = [
        FakeProvider("openai/x", "openai", "a"),
        FakeProvider("anthropic/y", "anthropic", "b"),
    ]
    reviews = Council(seats).run("artifact", "prompt")
    assert {r.provider for r in reviews} == {"openai", "anthropic"}


def test_council_excludes_generator_provider():
    seats = [
        FakeProvider("openai/x", "openai", "a"),
        FakeProvider("anthropic/y", "anthropic", "b"),
        FakeProvider("google/z", "google", "c"),
    ]
    reviews = Council(seats, generator_provider="anthropic").run("artifact", "prompt")
    providers = {r.provider for r in reviews}
    assert providers == {"openai", "google"}


def test_council_raises_when_all_seats_excluded():
    seats = [FakeProvider("openai/x", "openai")]
    with pytest.raises(ValueError, match="no seats"):
        Council(seats, generator_provider="openai").run("a", "p")


def test_council_surfaces_adapter_error_on_review():
    seats = [FakeProvider("openai/x", "openai"), FailingProvider()]
    reviews = Council(seats).run("a", "p")
    err = next(r for r in reviews if r.provider == "broken")
    assert err.error and "boom" in err.error
