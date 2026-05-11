from typing import Optional
from uuid import UUID
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import BrowserSession, Credential


class SessionsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_valid_session(self, user_id: UUID, platform: str) -> Optional[BrowserSession]:
        result = await self.session.execute(
            select(BrowserSession)
            .where(
                BrowserSession.user_id == user_id,
                BrowserSession.platform == platform,
                BrowserSession.is_valid == True,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_session(
        self,
        user_id: UUID,
        platform: str,
        storage_state: str,
        cookies_encrypted: Optional[str] = None,
        valid_days: int = 30,
    ) -> BrowserSession:
        existing = await self.session.execute(
            select(BrowserSession).where(
                BrowserSession.user_id == user_id,
                BrowserSession.platform == platform,
            )
        )
        session_obj = existing.scalar_one_or_none()
        expires = datetime.now(timezone.utc) + timedelta(days=valid_days)

        if session_obj:
            session_obj.storage_state = storage_state
            session_obj.cookies_encrypted = cookies_encrypted
            session_obj.is_valid = True
            session_obj.last_validated = datetime.now(timezone.utc)
            session_obj.expires_at = expires
        else:
            session_obj = BrowserSession(
                user_id=user_id,
                platform=platform,
                storage_state=storage_state,
                cookies_encrypted=cookies_encrypted,
                is_valid=True,
                last_validated=datetime.now(timezone.utc),
                expires_at=expires,
            )
            self.session.add(session_obj)
        await self.session.flush()
        return session_obj

    async def invalidate_session(self, user_id: UUID, platform: str) -> None:
        await self.session.execute(
            update(BrowserSession)
            .where(
                BrowserSession.user_id == user_id,
                BrowserSession.platform == platform,
            )
            .values(is_valid=False)
        )


class CredentialsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, user_id: UUID, platform: str) -> Optional[Credential]:
        result = await self.session.execute(
            select(Credential).where(
                Credential.user_id == user_id,
                Credential.platform == platform,
            )
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        user_id: UUID,
        platform: str,
        username_encrypted: str,
        password_encrypted: str,
    ) -> Credential:
        existing = await self.get(user_id, platform)
        if existing:
            existing.username_encrypted = username_encrypted
            existing.password_encrypted = password_encrypted
        else:
            existing = Credential(
                user_id=user_id,
                platform=platform,
                username_encrypted=username_encrypted,
                password_encrypted=password_encrypted,
            )
            self.session.add(existing)
        await self.session.flush()
        return existing
