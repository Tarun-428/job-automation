from typing import Optional
from uuid import UUID

from config.logging import get_logger
from db.database import get_db_session
from db.repositories.applications import ApplicationsRepository

logger = get_logger(__name__)


async def record_audit_log(
    application_id: Optional[UUID],
    user_id: Optional[UUID],
    event_type: str,
    event_data: Optional[dict] = None,
    ai_provider: Optional[str] = None,
    ai_model: Optional[str] = None,
    ai_confidence: Optional[float] = None,
) -> None:
    if not application_id or not user_id:
        return
    async with get_db_session() as session:
        repo = ApplicationsRepository(session)
        await repo.add_audit_log(
            application_id=application_id,
            user_id=user_id,
            event_type=event_type,
            event_data=event_data or {},
            ai_provider=ai_provider,
            ai_model=ai_model,
            ai_confidence=ai_confidence,
        )


async def record_screenshot(
    application_id: Optional[UUID],
    step_name: str,
    file_path: str,
) -> None:
    if not application_id or not file_path:
        return
    async with get_db_session() as session:
        repo = ApplicationsRepository(session)
        await repo.add_screenshot(
            application_id=application_id,
            step_name=step_name,
            file_path=file_path,
        )
