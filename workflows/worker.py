import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from config.settings import get_settings
from config.logging import configure_logging, get_logger
from workflows.apply_workflow import JobApplicationWorkflow
from workflows.activities.browser_activities import (
    navigate_and_analyze_activity,
    generate_resume_activity,
    fill_and_submit_activity,
    send_notification_activity,
)
from browser.context_manager import get_browser_manager
from db.database import create_tables

logger = get_logger(__name__)


async def run_worker() -> None:
    configure_logging()
    settings = get_settings()

    # Initialize DB
    await create_tables()

    # Initialize browser
    browser_manager = get_browser_manager()
    await browser_manager.start()

    # Connect to Temporal
    client = await Client.connect(settings.temporal_host, namespace=settings.temporal_namespace)

    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[JobApplicationWorkflow],
        activities=[
            navigate_and_analyze_activity,
            generate_resume_activity,
            fill_and_submit_activity,
            send_notification_activity,
        ],
    )

    logger.info("temporal_worker_starting", task_queue=settings.temporal_task_queue)
    try:
        await worker.run()
    finally:
        await browser_manager.stop()


if __name__ == "__main__":
    asyncio.run(run_worker())
