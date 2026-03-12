"""
ontology/embeddings.py
───────────────────────
Embedding generation for semantic search.
Uses OpenAI text-embedding-3-small (1536-dim).
Falls back to a deterministic mock when OPENAI_API_KEY is not set,
so the project runs end-to-end in demo/test environments without
an API key.
"""

from __future__ import annotations
import hashlib
import math
import os
from functools import lru_cache

_openai_client = None


def _get_client():
    global _openai_client
    if _openai_client is None:
        import openai
        _openai_client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _openai_client


def _mock_embedding(text: str, dims: int = 1536) -> list[float]:
    """
    Deterministic pseudo-embedding for dev/demo use.
    Reproducible for the same input, but NOT semantically meaningful.
    Replace with a real embedding model for production use.
    """
    seed = int(hashlib.md5(text.encode()).hexdigest(), 16)
    vec  = []
    for i in range(dims):
        # cheap pseudo-random float in [-1, 1]
        val = math.sin(seed * (i + 1) * 0.0001) 
        vec.append(val)
    # L2-normalize
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


async def get_embedding(text: str) -> list[float]:
    """
    Return a 1536-dim embedding vector for the given text.
    Uses OpenAI if OPENAI_API_KEY is set; otherwise uses mock.
    """
    if not os.getenv("OPENAI_API_KEY"):
        return _mock_embedding(text)

    try:
        client   = _get_client()
        response = await client.embeddings.create(
            model = "text-embedding-3-small",
            input = text,
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"[Embedding] OpenAI call failed ({e}), falling back to mock")
        return _mock_embedding(text)
