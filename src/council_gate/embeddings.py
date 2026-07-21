"""Sentence-embedding adapter.

Used by the entropy gate v2 to cluster semantically equivalent findings
across reviewers before scoring agreement. Importing this module is cheap;
the heavy sentence-transformers + torch stack only loads when a real
SentenceTransformerEmbedder is instantiated, so v1-only users don't pay
the install size.
"""
from __future__ import annotations

import hashlib
import logging
from collections.abc import Sequence
from typing import Protocol

log = logging.getLogger(__name__)

_DEFAULT_MODEL = "all-MiniLM-L6-v2"


class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class SentenceTransformerEmbedder:
    """Wraps sentence-transformers. Loads the model on first embed() call.

    Install: pip install council-gate[gate-v2]
    """

    def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
        self.model_name = model_name
        self._model = None  # lazy

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise RuntimeError(
                "sentence-transformers is not installed. "
                "Install with: pip install 'council-gate[gate-v2]'"
            ) from e
        log.info("loading embedder %s", self.model_name)
        self._model = SentenceTransformer(self.model_name)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        self._load()
        assert self._model is not None
        arr = self._model.encode(list(texts), convert_to_numpy=True, show_progress_bar=False)
        return arr.tolist()


class HashEmbedder:
    """Deterministic non-semantic embedder for tests and offline smoketests.

    Hashes each token to a fixed slot in a small vector. Two texts share
    similarity iff they share tokens. Not useful for production — the whole
    point of the v2 gate is semantic matching — but lets tests run without
    pulling torch.
    """

    def __init__(self, dim: int = 64) -> None:
        self.dim = dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            for tok in text.lower().split():
                h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
                vec[h % self.dim] += 1.0
            norm = sum(x * x for x in vec) ** 0.5
            if norm > 0:
                vec = [x / norm for x in vec]
            out.append(vec)
        return out
