"""AES-256-GCM payload encryption for API endpoints.

Usage (API clients):
  1. Encrypt request body:
       ciphertext_b64 = encrypt_payload(json.dumps(data).encode())
     Send with header:  X-Payload-Encrypted: 1
     Body:              the raw base64 string

  2. Decrypting a response that was auto-encrypted:
       plaintext = decrypt_payload(response_body_text)

Encoding format:
  base64( nonce[12 bytes] || ciphertext+tag )
  The GCM auth tag (16 bytes) is appended by cryptography to ciphertext.
"""
import base64
import logging
import os

from django.conf import settings

logger = logging.getLogger(__name__)

_NONCE_LEN = 12  # 96-bit nonce — NIST recommended for GCM
_MIN_CIPHER_LEN = _NONCE_LEN + 16  # nonce + 16-byte auth tag (empty plaintext)


def _get_key() -> bytes:
    key_b64 = getattr(settings, "PAYLOAD_ENCRYPTION_KEY", "").strip()
    if not key_b64:
        raise ValueError(
            "PAYLOAD_ENCRYPTION_KEY is not set. "
            "Generate with: python -c \"import os,base64; print(base64.b64encode(os.urandom(32)).decode())\""
        )
    key = base64.b64decode(key_b64)
    if len(key) != 32:
        raise ValueError("PAYLOAD_ENCRYPTION_KEY must base64-decode to exactly 32 bytes (AES-256).")
    return key


def encrypt_payload(plaintext: bytes) -> str:
    """
    Encrypt bytes with AES-256-GCM.
    Returns a base64-encoded string: nonce (12 B) || ciphertext+tag.
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(_NONCE_LEN)
    ciphertext = AESGCM(_get_key()).encrypt(nonce, plaintext, None)
    return base64.b64encode(nonce + ciphertext).decode()


def decrypt_payload(encoded: str) -> bytes:
    """
    Decrypt a base64-encoded payload produced by encrypt_payload.
    Raises ValueError on authentication failure or invalid input.
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.exceptions import InvalidTag
    try:
        raw = base64.b64decode(encoded)
    except Exception as exc:
        raise ValueError("Payload is not valid base64.") from exc

    if len(raw) < _MIN_CIPHER_LEN:
        raise ValueError("Encrypted payload is too short.")

    nonce, body = raw[:_NONCE_LEN], raw[_NONCE_LEN:]
    try:
        return AESGCM(_get_key()).decrypt(nonce, body, None)
    except InvalidTag as exc:
        logger.warning("AES-GCM authentication tag verification failed.")
        raise ValueError("Payload decryption failed: authentication tag mismatch.") from exc
    except Exception as exc:
        logger.warning("Payload decryption error: %s", exc)
        raise ValueError("Payload decryption failed.") from exc


def is_encryption_configured() -> bool:
    """Return True if PAYLOAD_ENCRYPTION_KEY is set and non-empty."""
    return bool(getattr(settings, "PAYLOAD_ENCRYPTION_KEY", "").strip())
