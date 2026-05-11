from uuid import UUID
from typing import Optional, Tuple

from security.vault import encrypt, decrypt
from db.database import get_db_session
from db.repositories.sessions import CredentialsRepository


class CredentialStore:
    async def save(self, user_id: UUID, platform: str, username: str, password: str) -> None:
        async with get_db_session() as session:
            repo = CredentialsRepository(session)
            await repo.upsert(
                user_id=user_id,
                platform=platform,
                username_encrypted=encrypt(username),
                password_encrypted=encrypt(password),
            )

    async def load(self, user_id: UUID, platform: str) -> Optional[Tuple[str, str]]:
        async with get_db_session() as session:
            repo = CredentialsRepository(session)
            cred = await repo.get(user_id, platform)
            if not cred:
                return None
            return decrypt(cred.username_encrypted), decrypt(cred.password_encrypted)
