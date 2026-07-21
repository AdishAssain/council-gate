"""CLI seams: gate-version validation and raw-review dumps."""
import json

import pytest

from council_gate.cli import _build_gate, _save_raw_reviews
from council_gate.gate import EntropyGate
from council_gate.types import OverallVerdict, Review


def test_build_gate_v1():
    assert isinstance(_build_gate("v1", threshold=0.35), EntropyGate)


def test_build_gate_rejects_unknown_version():
    # COUNCIL_GATE_VERSION bypasses argparse choices; must not fall back silently.
    with pytest.raises(SystemExit):
        _build_gate("v3", threshold=0.35)


def test_save_raw_reviews_includes_overall(tmp_path):
    r = Review(
        model_id="prov/model",
        provider="prov",
        findings=[],
        raw_text="{}",
        overall=OverallVerdict(recommendation="accept", severity="nit", rationale="ok"),
    )
    _save_raw_reviews(tmp_path, "artifact", [r])
    payload = json.loads((tmp_path / "artifact" / "prov__model.json").read_text())
    assert payload["overall"] == {
        "recommendation": "accept",
        "severity": "nit",
        "rationale": "ok",
    }


def test_save_raw_reviews_overall_none(tmp_path):
    r = Review(model_id="prov/model", provider="prov", findings=[], raw_text="x")
    _save_raw_reviews(tmp_path, "artifact", [r])
    payload = json.loads((tmp_path / "artifact" / "prov__model.json").read_text())
    assert payload["overall"] is None
