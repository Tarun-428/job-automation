import base64
import hashlib
from cryptography.fernet import Fernet
from config.settings import get_settings


def _get_fernet() -> Fernet:
    settings = get_settings()
    raw_key = settings.vault_encryption_key.encode()
    # Derive a 32-byte key using SHA-256 so any string key works
    derived = hashlib.sha256(raw_key).digest()
    b64_key = base64.urlsafe_b64encode(derived)
    return Fernet(b64_key)


def encrypt(plaintext: str) -> str:
    """Encrypt a string and return a base64url-encoded ciphertext."""
    fernet = _get_fernet()
    return fernet.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a base64url-encoded ciphertext and return plaintext."""
    fernet = _get_fernet()
    return fernet.decrypt(ciphertext.encode()).decode()


def encrypt_bytes(data: bytes) -> bytes:
    fernet = _get_fernet()
    return fernet.encrypt(data)


def decrypt_bytes(data: bytes) -> bytes:
    fernet = _get_fernet()
    return fernet.decrypt(data)
