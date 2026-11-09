"""Local sentence-transformers embeddings (no API cost, runs on CPU/MPS)."""
import os
from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer


@lru_cache(maxsize=1)
def model() -> SentenceTransformer:
    return SentenceTransformer(os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"))


def embed(texts: list[str]) -> np.ndarray:
    # normalised vectors: cosine similarity becomes a plain dot product
    return model().encode(texts, normalize_embeddings=True, convert_to_numpy=True)
