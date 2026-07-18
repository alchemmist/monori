"""Encryption for bank-connection secrets (credentials and cached sessions).

Secrets are encrypted at rest with a symmetric key read from the
``MONORI_ENCRYPTION_KEY`` environment variable (a urlsafe base64 32-byte Fernet
key). Without the key the bank-connection feature is simply unavailable — the
rest of the app runs unaffected.
"""

import json
import os


class CryptoUnavailable(RuntimeError):
    """Raised when a secret must be handled but no encryption key is configured."""


def available():
    return bool(os.environ.get("MONORI_ENCRYPTION_KEY"))


def generate_key():
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode()


def _fernet():
    key = os.environ.get("MONORI_ENCRYPTION_KEY")
    if not key:
        raise CryptoUnavailable("MONORI_ENCRYPTION_KEY is not set; bank connections are disabled")
    from cryptography.fernet import Fernet

    return Fernet(key.encode())


def encrypt(data):
    """Encrypt a JSON-serializable dict to an opaque token (bytes)."""
    return _fernet().encrypt(json.dumps(data).encode())


def decrypt(blob):
    """Decrypt a token produced by :func:`encrypt` back to its dict."""
    if blob is None:
        return None
    return json.loads(_fernet().decrypt(bytes(blob)).decode())
