from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.middleware.auth import APIKeyMiddleware
from api.middleware.rate_limit import RateLimitMiddleware
from api.routes import telegram as telegram_router
from api.routes import workflows as workflows_router
from api.routes import health as health_router
from config.settings import get_settings
from config.logging import configure_logging, get_logger
from db.database import create_tables, dispose_engine
from browser.context_manager import get_browser_manager

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    configure_logging()
    settings = get_settings()
    app.state.settings = settings

    # Initialize database
    await create_tables()
    logger.info("database_initialized")

    # Initialize browser manager
    browser_manager = get_browser_manager()
    await browser_manager.start()
    app.state.browser_manager = browser_manager
    logger.info("browser_manager_started")

    # Connect to Temporal
    try:
        from temporalio.client import Client
        temporal_client = await Client.connect(
            settings.temporal_host, namespace=settings.temporal_namespace
        )
        app.state.temporal_client = temporal_client
        logger.info("temporal_connected", host=settings.temporal_host)
    except Exception as e:
        logger.warning("temporal_unavailable", error=str(e))
        app.state.temporal_client = None

    # Initialize Telegram bot
    from telegram.notifications import TelegramNotifier
    from telegram.bot import TelegramBot

    notifier = TelegramNotifier()

    async def workflow_trigger_fn(
        user_id, telegram_user_id, job_url, workflow_id, application_id
    ):
        """Trigger workflow via Temporal or fallback to direct execution."""
        if app.state.temporal_client:
            from workflows.apply_workflow import JobApplicationWorkflow
            await app.state.temporal_client.start_workflow(
                JobApplicationWorkflow.run,
                args=[str(user_id), telegram_user_id, job_url, str(application_id)],
                id=workflow_id,
                task_queue=settings.temporal_task_queue,
            )
        else:
            # Fallback: run orchestrator directly (development mode)
            import asyncio
            from ai.router import AIRouter
            from agents.orchestrator import OrchestratorAgent, ApplicationState

            ai = AIRouter()
            orchestrator = OrchestratorAgent(ai, browser_manager, notifier)
            state = ApplicationState(
                user_id=user_id,
                telegram_user_id=telegram_user_id,
                job_url=job_url,
                workflow_id=workflow_id,
                application_id=application_id,
            )
            asyncio.create_task(orchestrator.run(state))

    bot = TelegramBot(notifier, workflow_trigger_fn)
    app.state.telegram_bot = bot
    logger.info("telegram_bot_initialized")

    yield

    # Shutdown
    await browser_manager.stop()
    await dispose_engine()
    logger.info("application_shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="JobBot — Autonomous AI Job Application Platform",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(APIKeyMiddleware)

    # Routes
    app.include_router(health_router.router)
    app.include_router(telegram_router.router)
    app.include_router(workflows_router.router)

    return app


app = create_app()
