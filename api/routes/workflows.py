import uuid
from typing import Optional

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from db.database import get_db_session
from db.repositories.users import UsersRepository
from db.repositories.applications import ApplicationsRepository
from config.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/workflows", tags=["workflows"])


class TriggerWorkflowRequest(BaseModel):
    telegram_user_id: int
    job_url: str


@router.post("/trigger")
async def trigger_workflow(body: TriggerWorkflowRequest, request: Request):
    """Manually trigger a job application workflow."""
    temporal_client = request.app.state.temporal_client

    async with get_db_session() as session:
        user_repo = UsersRepository(session)
        user, _ = await user_repo.get_or_create(body.telegram_user_id)

        if not user.onboarding_complete:
            raise HTTPException(status_code=400, detail="User onboarding not complete")

        workflow_id = f"apply-{uuid.uuid4().hex}"
        app_repo = ApplicationsRepository(session)
        application = await app_repo.create(
            user_id=user.id,
            job_url=body.job_url,
            workflow_id=workflow_id,
        )

    from workflows.apply_workflow import JobApplicationWorkflow
    from temporalio.client import WorkflowFailureError

    try:
        handle = await temporal_client.start_workflow(
            JobApplicationWorkflow.run,
            args=[str(user.id), body.telegram_user_id, body.job_url, str(application.id)],
            id=workflow_id,
            task_queue=request.app.state.settings.temporal_task_queue,
        )
        return {"workflow_id": workflow_id, "application_id": str(application.id)}
    except Exception as e:
        logger.error("workflow_start_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workflow_id}/status")
async def get_workflow_status(workflow_id: str, request: Request):
    """Get status of a running workflow."""
    async with get_db_session() as session:
        app_repo = ApplicationsRepository(session)
        app = await app_repo.get_by_workflow_id(workflow_id)
        if not app:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return {
            "workflow_id": workflow_id,
            "status": app.status,
            "job_title": app.job_title,
            "company": app.company,
            "error": app.error_message,
            "confirmation_id": app.confirmation_id,
        }
