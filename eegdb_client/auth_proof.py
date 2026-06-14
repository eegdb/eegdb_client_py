"""Challenge-response auth proof: SHA256(SHA256(token) || nonce)."""

from __future__ import annotations

import hashlib


def compute_proof(plaintext_token: str, nonce: bytes) -> bytes:
    token_hash = hashlib.sha256(plaintext_token.encode("utf-8")).digest()
    return hashlib.sha256(token_hash + nonce).digest()
