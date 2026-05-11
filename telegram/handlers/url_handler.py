import re
import uuid
from typing import Optional

from telegram.notifications import TelegramNotifier
from db.database import get_db_session
from db.repositories.users import UsersRepository
from db.repositories.applications import ApplicationsRepository
from config.logging import get_logger

logger = get_logger(__name__)

URL_RE = re.compile(
    r"https?://[^\s]+"
)


class URLHandler:
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    def extract_url(self, text: str) -> Optional[str]:
        match = URL_RE.search(text)
        return match.group(0) if match else None

    async def handle(
        self,
        telegram_user_id: int,
        telegram_username: Optional[str],
        text: str,
        workflow_trigger_fn,
    ) -> None:
        url = self.extract_url(text)
        if not url:
            await self.notifier.send_message(
                telegram_user_id,
                "❌ No valid URL found. Please send a direct job application URL."
            )
            return

        # Get or create user
        async with get_db_session() as session:
            user_repo = UsersRepository(session)
            user, created = await user_repo.get_or_create(telegram_user_id, telegram_username)

            if not user.onboarding_complete:
                await self.notifier.send_message(
                    telegram_user_id,
                    "👋 Welcome! Please complete your profile first.\n"
                    "Send /profile to set up your information."
                )
                return

            # Create application record
            workflow_id = f"apply-{uuid.uuid4().hex}"
            app_repo = ApplicationsRepository(session)
            application = await app_repo.create(
                user_id=user.id,
                job_url=url,
                workflow_id=workflow_id,
            )

        await self.notifier.send_message(
            telegram_user_id,
            f"🚀 Starting application workflow...\n\n"
            f"🔗 URL: {url[:80]}...\n"
            f"ID: `{workflow_id}`\n\n"
            f"I'll keep you updated. This may take a few minutes."
        )

        # Trigger async workflow
        await workflow_trigger_fn(
            user_id=user.id,
            telegram_user_id=telegram_user_id,
            job_url=url,
            workflow_id=workflow_id,
            application_id=application.id,
        )
