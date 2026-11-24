import hashlib
import math
import re

_TOKEN_RE = re.compile(r"[a-z0-9]{2,}")

_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "into",
        "under",
        "shall",
        "will",
        "not",
        "any",
        "all",
        "are",
        "was",
        "were",
        "has",
        "have",
        "been",
        "such",
        "per",
        "than",
        "other",
        "more",
        "which",
        "their",
        "they",
        "there",
        "here",
        "policy",
        "insured",
        "section",
    }
)


def tokenize(text: str) -> list[str]:
    """Extract normalized alphanumeric tokens filtering common stopwords."""
    raw = _TOKEN_RE.findall(text.lower())
    return [tok for tok in raw if tok not in _STOPWORDS]


def extract_keywords(text: str, max_keywords: int = 12) -> list[str]:
    """Return top deterministic keywords ordered by term frequency."""
    tokens = tokenize(text)
    counts: dict[str, int] = {}
    for tok in tokens:
        counts[tok] = counts.get(tok, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [word for word, _ in ranked[:max_keywords]]


def _hash_bucket(feature: str, dims: int) -> tuple[int, float]:
    digest = hashlib.sha256(feature.encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:4], "big") % dims
    sign = 1.0 if (digest[4] & 1) == 0 else -1.0
    return bucket, sign


def embed_text(text: str, dims: int = 384) -> list[float]:
    """Compute a deterministic L2-normalized hashed unigram+bigram embedding vector."""
    if dims <= 0:
        raise ValueError("Embedding dimensions must be positive.")
    vec = [0.0] * dims
    tokens = tokenize(text)
    if not tokens:
        return vec

    for tok in tokens:
        idx, sign = _hash_bucket(f"u:{tok}", dims)
        vec[idx] += sign

    for i in range(len(tokens) - 1):
        bigram = f"b:{tokens[i]}_{tokens[i + 1]}"
        idx, sign = _hash_bucket(bigram, dims)
        vec[idx] += sign * 1.25

    norm = math.sqrt(sum(v * v for v in vec))
    if norm <= 0.0:
        return vec
    return [round(v / norm, 6) for v in vec]


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two equal-length float vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=True))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a <= 0.0 or norm_b <= 0.0:
        return 0.0
    return max(-1.0, min(1.0, dot / (norm_a * norm_b)))
