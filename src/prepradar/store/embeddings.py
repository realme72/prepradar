"""Local sentence-transformers embeddings (no API cost, runs on CPU/MPS)."""
import os
from functools import lru_cache

# keep CLI output readable: no model-download progress bars or info logs
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TQDM_DISABLE", "1")

import numpy as np
from sentence_transformers import SentenceTransformer

# bge models are trained to put this prefix on short search queries (not on the
# documents being searched); it improves query -> question matching
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@lru_cache(maxsize=1)
def model() -> SentenceTransformer:
    return SentenceTransformer(os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"))


def embed(texts: list[str]) -> np.ndarray:
    # normalised vectors: cosine similarity becomes a plain dot product
    return model().encode(texts, normalize_embeddings=True, convert_to_numpy=True)


def embed_query(text: str) -> np.ndarray:
    return embed([QUERY_PREFIX + text])[0]
