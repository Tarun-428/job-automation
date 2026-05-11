import re
import uuid
from typing import Optional
from urllib.parse import urlparse

import httpx

from telegram.notifications import TelegramNotifier
from db.database import get_db_session
from db.repositories.users import UsersRepository
from db.repositories.applications import ApplicationsRepository
from config.logging import get_logger

logger = get_logger(__name__)

# General URL pattern
URL_RE = re.compile(r"https?://[^\s]+")

# Valid LinkedIn job posting URL pattern: linkedin.com/jobs/view/<numeric-id>
LINKEDIN_JOB_RE = re.compile(
    r"https?://(www\.)?linkedin\.com/jobs/view/\d+",
    re.IGNORECASE,
)


class URLHandler:
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    def extract_url(self, text: str) -> Optional[str]:
        """Extract the first URL from a text message."""
        match = URL_RE.search(text)
        return match.group(0) if match else None

    def is_linkedin_url(self, url: str) -> bool:
        """Return True when the URL's host is the LinkedIn domain.

        Uses ``urllib.parse`` to inspect the hostname rather than a simple
        substring check, which would incorrectly match URLs such as
        ``https://evil.com/redirect?to=linkedin.com``.
        """
        try:
            host = urlparse(url).hostname or ""
            return host == "linkedin.com" or host.endswith(".linkedin.com")
        except Exception:
            return False

    def is_valid_linkedin_job_url(self, url: str) -> bool:
        """Return True only for proper LinkedIn job-posting URLs.

        Valid form: https://www.linkedin.com/jobs/view/<numeric-id>
        """
        return bool(LINKEDIN_JOB_RE.match(url))

    async def check_url_reachable(self, url: str, timeout: float = 10.0) -> bool:
        """Send a HEAD request to verify the URL is reachable (non-4xx/5xx).

        Returns True when the server responds with a 2xx or 3xx status code.
        Network errors are treated as unreachable.
        """
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; JobBot/1.0)"},
            ) as client:
                response = await client.head(url)
                # Accept redirects (3xx) and success (2xx); reject 4xx/5xx
                return response.status_code < 400
        except Exception as exc:
            logger.warning("url_reachability_check_failed", url=url, error=str(exc))
            return False

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

        # --- LinkedIn-specific validation ---
        if self.is_linkedin_url(url):
            if not self.is_valid_linkedin_job_url(url):
                await self.notifier.send_message(
                    telegram_user_id,
                    "❌ *Invalid LinkedIn URL.*\n\n"
                    "Please send a direct LinkedIn job posting URL in the form:\n"
                    "`https://www.linkedin.com/jobs/view/<job-id>`\n\n"
                    "Make sure you copy the link from the job details page, not from a search result."
                )
                return

            # Verify the job posting is still live
            await self.notifier.send_typing(telegram_user_id)
            reachable = await self.check_url_reachable(url)
            if not reachable:
                await self.notifier.send_message(
                    telegram_user_id,
                    "❌ *LinkedIn job not found or has expired.*\n\n"
                    "The job posting at the provided URL does not exist or is no longer available.\n"
                    "Please verify the link and try again."
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
            f"🚀 *Application workflow started!*\n\n"
            f"🔗 URL: `{url[:80]}`\n"
            f"🆔 ID: `{workflow_id}`\n\n"
            f"I'll send you updates at each step. This may take a few minutes.\n"
            f"Use /update to check progress or /revert to cancel."
        )

        # Trigger async workflow
        await workflow_trigger_fn(
            user_id=user.id,
            telegram_user_id=telegram_user_id,
            job_url=url,
            workflow_id=workflow_id,
            application_id=application.id,
        )
