from typing import Callable, Awaitable, Optional

from telegram.notifications import TelegramNotifier
from telegram.handlers.url_handler import URLHandler
from telegram.handlers.otp_handler import OTPHandler
from telegram.handlers.approval_handler import ApprovalHandler
from telegram.handlers.question_handler import QuestionHandler
from db.database import get_db_session
from db.repositories.users import UsersRepository
from config.logging import get_logger

logger = get_logger(__name__)

HELP_TEXT = """
🤖 *JobBot — Autonomous Job Application AI*

*Commands:*
/start — Register and begin onboarding
/profile — Update your profile
/status — Check active applications
/history — View application history
/update — Get a detailed step-by-step progress report for your latest application
/revert — Cancel and roll back your latest pending/running application
/help — Show this message

*To apply to a job:*
Simply send the job application URL (LinkedIn, Indeed, Greenhouse, etc.) and I'll handle everything automatically!

*During application:*
• I'll ask you questions I can't answer automatically
• Send OTPs when requested
• Reply `yes`/`no` to approve final submissions

*LinkedIn URLs must follow this format:*
`https://www.linkedin.com/jobs/view/<job-id>`
"""

ONBOARDING_STEPS = [
    ("full_name", "👤 What is your full name?"),
    ("email", "📧 What is your email address?"),
    ("phone", "📱 What is your phone number?"),
    ("location", "📍 What is your current location? (City, Country)"),
    ("linkedin_url", "🔗 LinkedIn profile URL (or 'skip'):"),
    ("github_url", "💻 GitHub profile URL (or 'skip'):"),
    ("portfolio_url", "🌐 Portfolio/website URL (or 'skip'):"),
    ("notice_period", "⏰ What is your notice period? (e.g., Immediate, 2 weeks, 1 month)"),
    ("visa_status", "📋 What is your visa/work authorization status?"),
    ("skills", "🛠 List your top skills, comma-separated (e.g., Python, React, SQL):"),
    ("summary", "✍️ Write a brief professional summary (2-3 sentences):"),
]

# Emoji mapping for application statuses used across multiple handlers
STATUS_EMOJI = {
    "completed": "✅",
    "running": "🔄",
    "failed": "❌",
    "paused": "⏸",
    "pending": "⏳",
    "reverted": "↩️",
    "waiting_user": "🙋",
    "escalated": "⚠️",
}


class TelegramBot:
    def __init__(self, notifier: TelegramNotifier, workflow_trigger_fn: Callable):
        self.notifier = notifier
        self.url_handler = URLHandler(notifier)
        self.otp_handler = OTPHandler()
        self.approval_handler = ApprovalHandler()
        self.question_handler = QuestionHandler()
        self.workflow_trigger = workflow_trigger_fn
        self._onboarding_state: dict[int, dict] = {}  # In-memory onboarding state

    async def handle_update(self, update: dict) -> None:
        """Main entry point for all Telegram updates."""
        message = update.get("message") or update.get("edited_message")
        if not message:
            return

        chat_id = message["chat"]["id"]
        from_user = message.get("from", {})
        telegram_user_id = from_user.get("id", chat_id)
        telegram_username = from_user.get("username")
        text = message.get("text", "").strip()

        if not text:
            return

        logger.info("telegram_message", user=telegram_user_id, text=text[:80])

        # Command routing
        if text.startswith("/start"):
            await self._handle_start(telegram_user_id, telegram_username)
        elif text.startswith("/profile"):
            await self._handle_profile_start(telegram_user_id)
        elif text.startswith("/status"):
            await self._handle_status(telegram_user_id)
        elif text.startswith("/history"):
            await self._handle_history(telegram_user_id)
        elif text.startswith("/update"):
            await self._handle_update(telegram_user_id)
        elif text.startswith("/revert"):
            await self._handle_revert(telegram_user_id)
        elif text.startswith("/help"):
            await self.notifier.send_message(telegram_user_id, HELP_TEXT)
        elif telegram_user_id in self._onboarding_state:
            await self._handle_onboarding_step(telegram_user_id, text)
        elif "http" in text:
            await self.url_handler.handle(
                telegram_user_id, telegram_username, text, self.workflow_trigger
            )
        else:
            lowered = text.lower()
            if "linkedin" in lowered or "linkdin" in lowered:
                await self.notifier.send_message(
                    telegram_user_id,
                    "🔗 Please send the full LinkedIn job URL in this format:\n"
                    "`https://www.linkedin.com/jobs/view/<job-id>`\n\n"
                    "Once you send a valid link, I'll start the application.",
                )
                return
            # Route to escalation handler (OTP / approval / answer)
            handled = await self.otp_handler.handle(telegram_user_id, text)
            if not handled:
                await self.approval_handler.handle(telegram_user_id, text)

    async def _handle_start(self, telegram_user_id: int, username: Optional[str]) -> None:
        async with get_db_session() as session:
            repo = UsersRepository(session)
            user, created = await repo.get_or_create(telegram_user_id, username)

        if created or not user.onboarding_complete:
            await self.notifier.send_message(
                telegram_user_id,
                "👋 Welcome to *JobBot*! I'll autonomously apply to jobs for you.\n\n"
                "Let's set up your profile first. This will take 2 minutes.\n"
                "Send /profile to begin!"
            )
        else:
            await self.notifier.send_message(
                telegram_user_id,
                f"👋 Welcome back!\n\n{HELP_TEXT}"
            )

    async def _handle_profile_start(self, telegram_user_id: int) -> None:
        self._onboarding_state[telegram_user_id] = {"step": 0, "data": {}}
        step_key, question = ONBOARDING_STEPS[0]
        await self.notifier.send_message(
            telegram_user_id,
            f"📝 *Profile Setup* (1/{len(ONBOARDING_STEPS)})\n\n{question}"
        )

    async def _handle_onboarding_step(self, telegram_user_id: int, text: str) -> None:
        state = self._onboarding_state[telegram_user_id]
        step_idx = state["step"]
        step_key, _ = ONBOARDING_STEPS[step_idx]

        value = None if text.lower() == "skip" else text.strip()

        # Special parsing for skills
        if step_key == "skills" and value:
            value = {s.strip(): 3 for s in value.split(",")}  # default level 3

        if value:
            state["data"][step_key] = value

        state["step"] += 1
        next_step = state["step"]

        if next_step >= len(ONBOARDING_STEPS):
            # Complete onboarding
            profile_data = state["data"]
            async with get_db_session() as session:
                user_repo = UsersRepository(session)
                user = await user_repo.get_by_telegram_id(telegram_user_id)
                if user:
                    await user_repo.upsert_profile(user.id, profile_data)
                    await user_repo.update_onboarding(user.id, True)
            del self._onboarding_state[telegram_user_id]
            await self.notifier.send_message(
                telegram_user_id,
                "✅ *Profile complete!*\n\nNow send me any job application URL and I'll apply for you automatically!"
            )
        else:
            _, next_question = ONBOARDING_STEPS[next_step]
            await self.notifier.send_message(
                telegram_user_id,
                f"📝 *Profile Setup* ({next_step + 1}/{len(ONBOARDING_STEPS)})\n\n{next_question}"
            )

    async def _handle_status(self, telegram_user_id: int) -> None:
        async with get_db_session() as session:
            user_repo = UsersRepository(session)
            user = await user_repo.get_by_telegram_id(telegram_user_id)
            if not user:
                await self.notifier.send_message(telegram_user_id, "No account found. Send /start")
                return
            from db.repositories.applications import ApplicationsRepository
            app_repo = ApplicationsRepository(session)
            apps = await app_repo.list_by_user(user.id, limit=5)

        if not apps:
            await self.notifier.send_message(telegram_user_id, "No applications yet. Send a job URL to start!")
            return

        lines = ["📊 *Recent Applications:*\n"]
        for app in apps:
            status_emoji = STATUS_EMOJI.get(app.status, "❓")
            lines.append(f"{status_emoji} {app.job_title or 'Unknown'} @ {app.company or 'Unknown'} — {app.status}")

        await self.notifier.send_message(telegram_user_id, "\n".join(lines))

    async def _handle_history(self, telegram_user_id: int) -> None:
        await self._handle_status(telegram_user_id)

    async def _handle_update(self, telegram_user_id: int) -> None:
        """Send the user a detailed step-by-step status for their latest application."""
        async with get_db_session() as session:
            user_repo = UsersRepository(session)
            user = await user_repo.get_by_telegram_id(telegram_user_id)
            if not user:
                await self.notifier.send_message(telegram_user_id, "No account found. Send /start first.")
                return

            from db.repositories.applications import ApplicationsRepository
            app_repo = ApplicationsRepository(session)
            app = await app_repo.get_latest_by_user(user.id)

            if not app:
                await self.notifier.send_message(
                    telegram_user_id,
                    "No applications found. Send a job URL to start!"
                )
                return

            # Fetch audit logs for stepwise detail
            logs = await app_repo.get_audit_logs(app.id)

        status_emoji = STATUS_EMOJI.get(app.status, "❓")
        lines = [
            f"📋 *Application Update*\n",
            f"🔗 URL: `{(app.job_url or '')[:80]}`",
            f"💼 Job: {app.job_title or 'Unknown'} @ {app.company or 'Unknown'}",
            f"🆔 Workflow: `{app.workflow_id}`",
            f"📌 Status: {status_emoji} *{app.status}*",
        ]

        if app.error_message:
            lines.append(f"⚠️ Note: {app.error_message}")

        if logs:
            lines.append("\n*Step-by-step log:*")
            for log in logs:
                ts = log.created_at.strftime("%H:%M:%S") if log.created_at else "?"
                lines.append(f"  `{ts}` — {log.event_type}")
        else:
            lines.append("\n_No detailed log entries yet._")

        lines.append(
            "\nUse /revert to cancel this application or send a new URL to start another."
        )
        await self.notifier.send_message(telegram_user_id, "\n".join(lines))

    async def _handle_revert(self, telegram_user_id: int) -> None:
        """Cancel and roll back the user's latest pending/running application."""
        async with get_db_session() as session:
            user_repo = UsersRepository(session)
            user = await user_repo.get_by_telegram_id(telegram_user_id)
            if not user:
                await self.notifier.send_message(telegram_user_id, "No account found. Send /start first.")
                return

            from db.repositories.applications import ApplicationsRepository
            app_repo = ApplicationsRepository(session)
            app = await app_repo.get_latest_by_user(user.id)

            if not app:
                await self.notifier.send_message(
                    telegram_user_id,
                    "No applications found. Nothing to revert."
                )
                return

            # Only revert if the application is still in a cancellable state
            if app.status in ("completed", "reverted"):
                status_emoji = STATUS_EMOJI.get(app.status, "❓")
                await self.notifier.send_message(
                    telegram_user_id,
                    f"ℹ️ Your latest application is already *{app.status}* {status_emoji}.\n"
                    "There is nothing to revert."
                )
                return

            await app_repo.revert(app.id, reason="user_requested_via_telegram")

        await self.notifier.send_message(
            telegram_user_id,
            f"↩️ *Application reverted.*\n\n"
            f"💼 {app.job_title or 'Unknown'} @ {app.company or 'Unknown'}\n"
            f"🆔 `{app.workflow_id}`\n\n"
            "The application has been cancelled and marked as reverted. "
            "Send a new job URL whenever you're ready to try again."
        )
