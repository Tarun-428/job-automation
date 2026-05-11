from temporalio import activity
from typing import Optional
from uuid import UUID
import uuid as _uuid

from config.logging import get_logger

logger = get_logger(__name__)


@activity.defn
async def navigate_and_analyze_activity(
    user_id: str,
    job_url: str,
    telegram_user_id: int,
) -> dict:
    """Navigate to job URL and extract basic info."""
    from browser.context_manager import get_browser_manager
    from agents.vision import VisionAgent
    from agents.job_parser import JobParserAgent
    from agents.browser_nav import BrowserNavAgent
    from ai.router import AIRouter

    ai = AIRouter()
    vision = VisionAgent(ai)
    browser_nav = BrowserNavAgent(vision)
    job_parser = JobParserAgent(ai)
    browser_manager = get_browser_manager()

    uid = UUID(user_id)
    platform = job_parser.detect_platform(job_url)
    context, session_loaded = await browser_manager.load_session_context(uid, platform)
    page = await context.new_page()

    try:
        await browser_nav.navigate_to_url(page, job_url)
        await browser_nav.handle_popup(page)
        raw_text = await browser_nav.extract_page_text(page)
        parsed = await job_parser.parse_job_description(raw_text, job_url)
        return {
            "platform": platform,
            "raw_jd": raw_text,
            "job_title": parsed.job_title,
            "company": parsed.company,
            "required_skills": parsed.required_skills,
        }
    finally:
        await page.close()
        await context.close()


@activity.defn
async def generate_resume_activity(user_id: str, raw_jd: str, application_id: str) -> Optional[str]:
    """Generate a tailored resume PDF and return its path."""
    from agents.memory import MemoryAgent
    from agents.job_parser import JobParserAgent, ParsedJob
    from agents.resume_gen import ResumeGenerationAgent
    from ai.router import AIRouter

    ai = AIRouter()
    memory = MemoryAgent()
    uid = UUID(user_id)
    aid = UUID(application_id)

    resume_agent = ResumeGenerationAgent(ai, memory)

    # Build a minimal ParsedJob from the raw JD
    job_parser = JobParserAgent(ai)
    parsed = await job_parser.parse_job_description(raw_jd)

    pdf_path = await resume_agent.generate_tailored_resume(uid, parsed, aid)
    return pdf_path


@activity.defn
async def fill_and_submit_activity(
    user_id: str,
    telegram_user_id: int,
    job_url: str,
    platform: str,
    application_id: str,
    resume_pdf_path: Optional[str],
) -> dict:
    """Fill form, upload resume, validate and submit application."""
    from browser.context_manager import get_browser_manager
    from agents.vision import VisionAgent
    from agents.browser_nav import BrowserNavAgent
    from agents.login_auth import LoginAuthAgent
    from agents.form_fill import FormFillerAgent
    from agents.validation import ValidationAgent
    from agents.escalation import EscalationAgent
    from agents.memory import MemoryAgent
    from ai.router import AIRouter
    from security.credential_store import CredentialStore
    from telegram.notifications import TelegramNotifier
    from browser.screenshot import capture_screenshot

    ai = AIRouter()
    vision = VisionAgent(ai)
    memory = MemoryAgent()
    browser_nav = BrowserNavAgent(vision)
    cred_store = CredentialStore()
    login_auth = LoginAuthAgent(vision, cred_store)
    notifier = TelegramNotifier()
    escalation = EscalationAgent(notifier)
    form_filler = FormFillerAgent(ai, vision, memory)
    validator = ValidationAgent(vision)
    browser_manager = get_browser_manager()

    uid = UUID(user_id)
    aid = UUID(application_id)

    context, _ = await browser_manager.load_session_context(uid, platform)
    page = await context.new_page()

    result = {
        "submitted": False,
        "confirmation_id": None,
        "error": None,
        "fields_filled": 0,
    }

    try:
        await browser_nav.navigate_to_url(page, job_url)
        await browser_nav.handle_popup(page)
        await browser_nav.smart_navigate_apply(page, uid)

        # Login if needed
        await login_auth.ensure_logged_in(page, platform, uid, telegram_user_id, escalation)

        # Fill form
        filled = await form_filler.fill_all_visible_fields(page, uid, telegram_user_id, escalation)
        result["fields_filled"] = len(filled)

        # Upload resume
        if resume_pdf_path:
            await browser_nav.handle_file_upload(page, resume_pdf_path)

        # Validate
        validation = await validator.validate_before_submit(page, uid)
        if not validation.passed:
            result["error"] = f"Validation failed: {validation.errors}"
            return result

        # Take pre-submit screenshot for approval
        screenshot_bytes, _ = await capture_screenshot(page, "pre_submit", str(uid))
        summary = f"Fields filled: {len(filled)}\nResume: {'uploaded' if resume_pdf_path else 'not uploaded'}"
        approved = await escalation.request_approval(telegram_user_id, summary, screenshot_bytes)

        if not approved:
            result["error"] = "User did not approve submission"
            return result

        # Submit
        for sel in ['button[type="submit"]', 'button:has-text("Submit")', 'button:has-text("Apply")']:
            try:
                await page.click(sel, timeout=5000)
                await page.wait_for_load_state("networkidle", timeout=15000)
                break
            except Exception:
                continue

        from agents.vision import VisionAgent as VA
        screenshot_bytes2, _ = await capture_screenshot(page, "post_submit", str(uid))
        success = await vision.detect_success(screenshot_bytes2)
        result["submitted"] = success

        # Save session
        await browser_manager.save_session(uid, platform, context)

    except Exception as e:
        result["error"] = str(e)
        logger.error("fill_submit_activity_error", error=str(e))
    finally:
        await page.close()
        await context.close()

    return result


@activity.defn
async def send_notification_activity(
    telegram_user_id: int,
    message: str,
) -> None:
    """Send a Telegram message to the given user."""
    from telegram.notifications import TelegramNotifier
    notifier = TelegramNotifier()
    await notifier.send_message(telegram_user_id, message)


@activity.defn
async def update_application_status_activity(
    application_id: str,
    status: str,
    error_message: Optional[str] = None,
) -> None:
    """Persist an application status change to the database.

    This is used by the workflow to record auto-reverts and other
    status transitions without coupling the workflow logic to the ORM.
    When status is 'reverted', the repository's revert() API is used to
    preserve its guardrails against reverting completed records.
    """
    from db.database import get_db_session
    from db.repositories.applications import ApplicationsRepository
    from uuid import UUID

    aid = UUID(application_id)
    async with get_db_session() as session:
        repo = ApplicationsRepository(session)
        if status == "reverted":
            await repo.revert(aid, reason=error_message or "auto_reverted")
        else:
            await repo.update_status(aid, status=status, error_message=error_message)
