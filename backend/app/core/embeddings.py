"""Local deterministic embeddings used for semantic memory retrieval.

This is NOT a language model embedding. It is a hashed character/word n-gram
projection that provides stable, deterministic similarity search with zero
network dependencies. If NOESIS_LLM_API_KEY is configured and
NOESIS_EMBEDDING_PROVIDER=openai, the OpenAI embedding endpoint is used instead.
"""
import hashlib
import math
import re

from app.core.config import settings

_DIM = 256
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def local_embed(text: str, dim: int = _DIM) -> list[float]:
    """Deterministic hashed n-gram embedding, L2-normalized."""
    vec = [0.0] * dim
    tokens = _TOKEN_RE.findall(text.lower())
    for token in tokens:
        for gram, weight in (
            (token, 1.0),
            (f"#{token}", 0.5),
        ):
            h = int.from_bytes(hashlib.blake2b(gram.encode(), digest_size=8).digest(), "big")
            vec[h % dim] += weight
            # character trigrams add robustness to short scientific terms
        for i in range(len(token) - 2):
            tri = token[i : i + 3]
            h = int.from_bytes(hashlib.blake2b(tri.encode(), digest_size=8).digest(), "big")
            vec[h % dim] += 0.1
    return _normalize(vec)


def openai_embed(texts: list[str]) -> list[list[float]] | None:
    """Best-effort OpenAI embeddings; returns None if unavailable."""
    if not settings.llm_api_key:
        return None
    try:
        import httpx

        resp = httpx.post(
            f"{settings.llm_base_url or 'https://api.openai.com/v1'}/embeddings",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            json={"model": "text-embedding-3-small", "input": texts},
            timeout=30,
        )
        resp.raise_for_status()
        return [item["embedding"] for item in resp.json()["data"]]
    except Exception:
        return None


def embed_text(text: str) -> list[float]:
    if settings.embedding_provider == "openai":
        vectors = openai_embed([text])
        if vectors:
            return vectors[0]
    return local_embed(text)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))  # vectors are L2-normalized
