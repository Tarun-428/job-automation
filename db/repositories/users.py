from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import User, UserProfile


class UsersRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_telegram_id(self, telegram_user_id: int) -> Optional[User]:
        result = await self.session.execute(
            select(User)
            .options(selectinload(User.profile))
            .where(User.telegram_user_id == telegram_user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        result = await self.session.execute(
            select(User)
            .options(selectinload(User.profile))
            .where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def create(self, telegram_user_id: int, telegram_username: Optional[str] = None) -> User:
        user = User(
            telegram_user_id=telegram_user_id,
            telegram_username=telegram_username,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def get_or_create(self, telegram_user_id: int, telegram_username: Optional[str] = None) -> tuple[User, bool]:
        user = await self.get_by_telegram_id(telegram_user_id)
        if user:
            return user, False
        user = await self.create(telegram_user_id, telegram_username)
        return user, True

    async def update_onboarding(self, user_id: UUID, complete: bool) -> None:
        await self.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(onboarding_complete=complete)
        )

    async def upsert_profile(self, user_id: UUID, profile_data: dict) -> UserProfile:
        result = await self.session.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        )
        profile = result.scalar_one_or_none()
        if profile:
            for key, value in profile_data.items():
                if hasattr(profile, key):
                    setattr(profile, key, value)
        else:
            profile = UserProfile(user_id=user_id, **profile_data)
            self.session.add(profile)
        await self.session.flush()
        return profile
