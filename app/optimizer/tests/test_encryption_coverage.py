"""
Coverage tests for optimizer.encryption — AES-256-GCM encrypt/decrypt.
Uses a real key (generated inline) with the cryptography library.
"""
import base64
import os
import pytest
from unittest.mock import patch, MagicMock


def _b64_key(n_bytes: int = 32) -> str:
    return base64.b64encode(os.urandom(n_bytes)).decode()


# ===========================================================================
# is_encryption_configured
# ===========================================================================

class TestIsEncryptionConfigured:
    def test_returns_false_when_key_not_set(self, settings):
        settings.PAYLOAD_ENCRYPTION_KEY = ""
        from optimizer import encryption
        assert encryption.is_encryption_configured() is False

    def test_returns_true_when_key_set(self, settings):
        settings.PAYLOAD_ENCRYPTION_KEY = _b64_key()
        from optimizer import encryption
        assert encryption.is_encryption_configured() is True

    def test_returns_false_when_key_is_whitespace(self, settings):
        settings.PAYLOAD_ENCRYPTION_KEY = "   "
        from optimizer import encryption
        assert encryption.is_encryption_configured() is False


# ===========================================================================
# _get_key
# ===========================================================================

class TestGetKey:
    def test_raises_when_key_not_set(self, settings):
        settings.PAYLOAD_ENCRYPTION_KEY = ""
        from optimizer import encryption
        with pytest.raises(ValueError, match="PAYLOAD_ENCRYPTION_KEY is not set"):
            encryption._get_key()

    def test_raises_when_key_wrong_length(self, settings):
        settings.PAYLOAD_ENCRYPTION_KEY = base64.b64encode(b"too-short").decode()
        from optimizer import encryption
        with pytest.raises(ValueError, match="32 bytes"):
            encryption._get_key()

    def test_returns_32_bytes(self, settings):
        settings.PAYLOAD_ENCRYPTION_KEY = _b64_key(32)
        from optimizer import encryption
        key = encryption._get_key()
        assert isinstance(key, bytes)
        assert len(key) == 32


# ===========================================================================
# encrypt_payload / decrypt_payload
# ===========================================================================

class TestEncryptDecrypt:
    @pytest.fixture(autouse=True)
    def set_key(self, settings):
        settings.PAYLOAD_ENCRYPTION_KEY = _b64_key(32)

    def test_encrypt_returns_string(self):
        from optimizer import encryption
        result = encryption.encrypt_payload(b"hello world")
        assert isinstance(result, str)

    def test_decrypt_roundtrip(self):
        from optimizer import encryption
        plaintext = b"secret data payload"
        encrypted = encryption.encrypt_payload(plaintext)
        decrypted = encryption.decrypt_payload(encrypted)
        assert decrypted == plaintext

    def test_encrypted_output_is_base64(self):
        from optimizer import encryption
        encrypted = encryption.encrypt_payload(b"test")
        base64.b64decode(encrypted)  # should not raise

    def test_different_encryptions_produce_different_ciphertexts(self):
        from optimizer import encryption
        enc1 = encryption.encrypt_payload(b"same")
        enc2 = encryption.encrypt_payload(b"same")
        assert enc1 != enc2  # nonce is random

    def test_decrypt_raises_on_invalid_base64(self):
        from optimizer import encryption
        with pytest.raises(ValueError, match="not valid base64"):
            encryption.decrypt_payload("not-valid-base64!!!")

    def test_decrypt_raises_on_too_short_payload(self):
        from optimizer import encryption
        short = base64.b64encode(b"tooshort").decode()
        with pytest.raises(ValueError, match="too short"):
            encryption.decrypt_payload(short)

    def test_decrypt_raises_on_tampered_payload(self):
        from optimizer import encryption
        encrypted = encryption.encrypt_payload(b"real data")
        raw = bytearray(base64.b64decode(encrypted))
        raw[-1] ^= 0xFF  # flip a bit in the tag
        tampered = base64.b64encode(bytes(raw)).decode()
        with pytest.raises(ValueError, match="decryption failed"):
            encryption.decrypt_payload(tampered)

    def test_encrypt_empty_bytes(self):
        from optimizer import encryption
        encrypted = encryption.encrypt_payload(b"")
        decrypted = encryption.decrypt_payload(encrypted)
        assert decrypted == b""

    def test_encrypt_large_payload(self):
        from optimizer import encryption
        big = os.urandom(1024 * 100)  # 100 KB
        encrypted = encryption.encrypt_payload(big)
        assert encryption.decrypt_payload(encrypted) == big
