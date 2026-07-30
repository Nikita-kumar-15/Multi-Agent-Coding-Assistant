# backend/utils/hashing.py
"""Content hashing utility for deduplication."""

import hashlib


def content_hash(*parts: str) -> str:
    """Returns a SHA-256 hex digest of the concatenated parts."""
    combined = "|".join(str(p) for p in parts)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()
