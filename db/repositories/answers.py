import hashlib
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AnswerHistory


class AnswersRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _hash_question(question: str) -> str:
        normalized = question.strip().lower()
        return hashlib.sha256(normalized.encode()).hexdigest()

    async def find_previous_answer(
        self, user_id: UUID, question_text: str
    ) -> Optional[AnswerHistory]:
        q_hash = self._hash_question(question_text)
        result = await self.session.execute(
            select(AnswerHistory).where(
                AnswerHistory.user_id == user_id,
                AnswerHistory.question_hash == q_hash,
            )
        )
        return result.scalar_one_or_none()

    async def record_answer(
        self,
        user_id: UUID,
        question_text: str,
        answer_value: str,
        confidence: float,
    ) -> AnswerHistory:
        q_hash = self._hash_question(question_text)
        existing = await self.find_previous_answer(user_id, question_text)
        if existing:
            existing.answer_value = answer_value
            existing.confidence = confidence
            existing.use_count += 1
            await self.session.flush()
            return existing
        record = AnswerHistory(
            user_id=user_id,
            question_hash=q_hash,
            question_text=question_text,
            answer_value=answer_value,
            confidence=confidence,
        )
        self.session.add(record)
        await self.session.flush()
        return record
