from typing import Optional
from uuid import UUID

from db.database import get_db_session
from db.repositories.users import UsersRepository
from db.repositories.answers import AnswersRepository
from config.logging import get_logger

logger = get_logger(__name__)


class MemoryAgent:
    """Provides user profile and answer history to other agents."""

    async def get_profile(self, user_id: UUID) -> Optional[dict]:
        async with get_db_session() as session:
            repo = UsersRepository(session)
            user = await repo.get_by_id(user_id)
            if not user or not user.profile:
                return None
            p = user.profile
            return {
                "full_name": p.full_name,
                "email": p.email,
                "phone": p.phone,
                "linkedin_url": p.linkedin_url,
                "github_url": p.github_url,
                "portfolio_url": p.portfolio_url,
                "location": p.location,
                "visa_status": p.visa_status,
                "work_authorization": p.work_authorization or [],
                "notice_period": p.notice_period,
                "salary_min": p.salary_min,
                "salary_max": p.salary_max,
                "preferred_locations": p.preferred_locations or [],
                "skills": p.skills or {},
                "experience": p.experience or [],
                "education": p.education or [],
                "certifications": p.certifications or [],
                "languages": p.languages or [],
                "summary": p.summary,
            }

    async def get_previous_answer(
        self, user_id: UUID, question_text: str
    ) -> Optional[dict]:
        async with get_db_session() as session:
            repo = AnswersRepository(session)
            record = await repo.find_previous_answer(user_id, question_text)
            if not record:
                return None
            return {
                "answer": record.answer_value,
                "confidence": record.confidence,
                "use_count": record.use_count,
            }

    async def save_answer(
        self,
        user_id: UUID,
        question_text: str,
        answer_value: str,
        confidence: float,
    ) -> None:
        async with get_db_session() as session:
            repo = AnswersRepository(session)
            await repo.record_answer(user_id, question_text, answer_value, confidence)

    async def update_profile(self, user_id: UUID, profile_data: dict) -> None:
        async with get_db_session() as session:
            repo = UsersRepository(session)
            await repo.upsert_profile(user_id, profile_data)
