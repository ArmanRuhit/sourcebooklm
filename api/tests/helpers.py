"""Deterministic embeddings for tests (no network, cosine-friendly)."""

import hashlib
import math
import re

from langchain_core.embeddings import Embeddings


class FakeEmbeddings(Embeddings):
    """Bag-of-words vectors: shared tokens score higher than unrelated text."""

    def __init__(self, dimensions: int = 1536) -> None:
        self.dimensions = dimensions

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in re.findall(r"[a-z0-9]+", text.lower()):
            digest = hashlib.sha256(token.encode()).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[bucket] += 1.0

        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)
