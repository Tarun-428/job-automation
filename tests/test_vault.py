import pytest
from unittest.mock import patch
from security.vault import encrypt, decrypt


def test_encrypt_decrypt_roundtrip():
    plaintext = "my-secret-password-123"
    ciphertext = encrypt(plaintext)
    assert ciphertext != plaintext
    result = decrypt(ciphertext)
    assert result == plaintext


def test_encrypt_produces_different_ciphertexts():
    plaintext = "same-password"
    c1 = encrypt(plaintext)
    c2 = encrypt(plaintext)
    # Fernet uses random IVs so each encryption is different
    assert c1 != c2


def test_decrypt_wrong_key_raises():
    plaintext = "secret"
    ciphertext = encrypt(plaintext)
    with patch("security.vault._get_fernet") as mock_fernet:
        from cryptography.fernet import Fernet
        wrong_key = Fernet.generate_key()
        mock_fernet.return_value = Fernet(wrong_key)
        with pytest.raises(Exception):
            decrypt(ciphertext)
