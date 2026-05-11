from security.vault import encrypt, decrypt


def encrypt_storage_state(storage_state_json: str) -> str:
    return encrypt(storage_state_json)


def decrypt_storage_state(encrypted: str) -> str:
    return decrypt(encrypted)
