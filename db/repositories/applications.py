from typing import Optional, List
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import Application, AIAnswer, AuditLog, Screenshot

NON_REVERTIBLE_STATUSES = ["completed", "reverted"]


class ApplicationsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        user_id: UUID,
        job_url: str,
        workflow_id: str,
    ) -> Application:
        app = Application(
            user_id=user_id,
            job_url=job_url,
            workflow_id=workflow_id,
        )
        self.session.add(app)
        await self.session.flush()
        return app

    async def get_by_workflow_id(self, workflow_id: str) -> Optional[Application]:
        result = await self.session.execute(
            select(Application)
            .options(
                selectinload(Application.ai_answers),
                selectinload(Application.screenshots),
            )
            .where(Application.workflow_id == workflow_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, application_id: UUID) -> Optional[Application]:
        result = await self.session.execute(
            select(Application).where(Application.id == application_id)
        )
        return result.scalar_one_or_none()

    async def list_by_user(self, user_id: UUID, limit: int = 50) -> List[Application]:
        result = await self.session.execute(
            select(Application)
            .where(Application.user_id == user_id)
            .order_by(Application.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_latest_by_user(self, user_id: UUID) -> Optional[Application]:
        """Return the most recent application for a user, or None."""
        result = await self.session.execute(
            select(Application)
            .where(Application.user_id == user_id)
            .order_by(Application.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_audit_logs(self, application_id: UUID) -> List[AuditLog]:
        """Return all audit-log entries for an application, ordered oldest-first."""
        result = await self.session.execute(
            select(AuditLog)
            .where(AuditLog.application_id == application_id)
            .order_by(AuditLog.created_at.asc())
        )
        return list(result.scalars().all())

    async def revert(
        self,
        application_id: UUID,
        reason: str = "user_requested",
    ) -> None:
        """Mark an application as 'reverted' and store the reason in error_message.

        Only applications that are not already completed or reverted will be
        updated, so calling this on a finished application is a no-op.
        """
        await self.session.execute(
            update(Application)
            .where(
                Application.id == application_id,
                Application.status.not_in(NON_REVERTIBLE_STATUSES),
            )
            .values(status="reverted", error_message=reason)
        )

    async def update_status(
        self,
        application_id: UUID,
        status: str,
        error_message: Optional[str] = None,
        job_title: Optional[str] = None,
        company: Optional[str] = None,
        platform: Optional[str] = None,
        confirmation_id: Optional[str] = None,
    ) -> None:
        values: dict = {"status": status}
        if error_message is not None:
            values["error_message"] = error_message
        if job_title is not None:
            values["job_title"] = job_title
        if company is not None:
            values["company"] = company
        if platform is not None:
            values["platform"] = platform
        if confirmation_id is not None:
            values["confirmation_id"] = confirmation_id
        await self.session.execute(
            update(Application).where(Application.id == application_id).values(**values)
        )

    async def add_ai_answer(
        self,
        application_id: UUID,
        question_text: str,
        answer_value: str,
        confidence: float,
        classification: str,
        question_type: str = "text",
        was_escalated: bool = False,
        user_provided: bool = False,
    ) -> AIAnswer:
        answer = AIAnswer(
            application_id=application_id,
            question_text=question_text,
            question_type=question_type,
            answer_value=answer_value,
            confidence=confidence,
            classification=classification,
            was_escalated=was_escalated,
            user_provided=user_provided,
        )
        self.session.add(answer)
        await self.session.flush()
        return answer

    async def add_audit_log(
        self,
        application_id: UUID,
        user_id: UUID,
        event_type: str,
        event_data: dict,
        ai_provider: Optional[str] = None,
        ai_model: Optional[str] = None,
        ai_confidence: Optional[float] = None,
    ) -> AuditLog:
        log = AuditLog(
            application_id=application_id,
            user_id=user_id,
            event_type=event_type,
            event_data=event_data,
            ai_provider=ai_provider,
            ai_model=ai_model,
            ai_confidence=ai_confidence,
        )
        self.session.add(log)
        await self.session.flush()
        return log

    async def add_screenshot(
        self,
        application_id: UUID,
        step_name: str,
        file_path: str,
    ) -> Screenshot:
        screenshot = Screenshot(
            application_id=application_id,
            step_name=step_name,
            file_path=file_path,
        )
        self.session.add(screenshot)
        await self.session.flush()
        return screenshot
