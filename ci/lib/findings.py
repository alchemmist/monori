"""Build stable identifiers for findings emitted by CI checks."""

import hashlib

FINDING_ID_LENGTH = 12


def stable_finding_id(raw_id: str, disambiguator: str = "") -> str:
    """Hash a semantic identity and optional duplicate discriminator into a stable ID."""
    return hashlib.sha256(f"{raw_id}{disambiguator}".encode()).hexdigest()[:FINDING_ID_LENGTH]
