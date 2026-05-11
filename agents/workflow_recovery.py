from typing import Optional
from uuid import UUID

from db.database import get_db_session
from db.repositories.applications import ApplicationsRepository
from config.logging import get_logger

logger = get_logger(__name__)


class WorkflowRecoveryAgent:
    """
    Handles crash recovery, retry coordination, and workflow state repair.
    Works alongside Temporal's built-in retry but adds application-level logic.
    """

    async def mark_failed(
        self,
        application_id: UUID,
        user_id: UUID,
        error: str,
        step: str,
    ) -> None:
        async with get_db_session() as session:
            repo = ApplicationsRepository(session)
            await repo.update_status(
                application_id=application_id,
                status="failed",
                error_message=f"[{step}] {error}",
            )
            await repo.add_audit_log(
                application_id=application_id,
                user_id=user_id,
                event_type="workflow_failed",
                event_data={"step": step, "error": error},
            )

    async def mark_paused(
        self,
        application_id: UUID,
        user_id: UUID,
        reason: str,
    ) -> None:
        async with get_db_session() as session:
            repo = ApplicationsRepository(session)
            await repo.update_status(
                application_id=application_id,
                status="paused",
                error_message=reason,
            )

    async def mark_waiting_user(self, application_id: UUID) -> None:
        async with get_db_session() as session:
            repo = ApplicationsRepository(session)
            await repo.update_status(
                application_id=application_id,
                status="waiting_user",
            )

    async def mark_running(self, application_id: UUID) -> None:
        async with get_db_session() as session:
            repo = ApplicationsRepository(session)
            await repo.update_status(
                application_id=application_id,
                status="running",
            )

    async def mark_completed(
        self,
        application_id: UUID,
        user_id: UUID,
        confirmation_id: Optional[str] = None,
    ) -> None:
        from datetime import datetime, timezone
        async with get_db_session() as session:
            repo = ApplicationsRepository(session)
            await repo.update_status(
                application_id=application_id,
                status="completed",
                confirmation_id=confirmation_id,
            )
            await repo.add_audit_log(
                application_id=application_id,
                user_id=user_id,
                event_type="application_submitted",
                event_data={"confirmation_id": confirmation_id},
            )

    async def can_retry(self, workflow_id: str, max_retries: int = 3) -> bool:
        """Check if a workflow can be retried based on attempt count."""
        import redis.asyncio as aioredis
        from config.settings import get_settings
        settings = get_settings()
        r = await aioredis.from_url(settings.redis_url)
        key = f"workflow:retries:{workflow_id}"
        count = await r.incr(key)
        await r.expire(key, 86400)
        return int(count) <= max_retries
