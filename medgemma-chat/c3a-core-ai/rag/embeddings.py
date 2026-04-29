"""Local embedding provider used by Qdrant ingestion and retrieval."""

from __future__ import annotations

from functools import cached_property
from typing import Iterable


class EmbeddingProvider:
    def __init__(self, model_name: str):
        self.model_name = model_name

    @cached_property
    def _model(self):
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise RuntimeError(
                "fastembed is not installed. Install backend requirements with "
                "`pip install -r c3a-core-ai/requirements.txt`."
            ) from exc

        return TextEmbedding(model_name=self.model_name)

    @cached_property
    def dimension(self) -> int:
        sample = self.embed_texts(["dimension probe"])[0]
        return len(sample)

    def embed_texts(self, texts: Iterable[str]) -> list[list[float]]:
        vectors = []
        for vector in self._model.embed(list(texts)):
            if hasattr(vector, "tolist"):
                vectors.append(vector.tolist())
            else:
                vectors.append(list(vector))
        return vectors
