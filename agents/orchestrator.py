from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional, Annotated
from uuid import UUID

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages

from ai.router import AIRouter
from agents.memory import MemoryAgent
from agents.vision import VisionAgent
from agents.job_parser import JobParserAgent
from agents.browser_nav import BrowserNavAgent
from agents.login_auth import LoginAuthAgent
from agents.form_fill import FormFillerAgent
from agents.resume_gen import ResumeGenerationAgent
from agents.validation import ValidationAgent
from agents.escalation import EscalationAgent
from agents.workflow_recovery import WorkflowRecoveryAgent
from browser.context_manager import BrowserContextManager
from browser.screenshot import capture_screenshot
from security.credential_store import CredentialStore
from telegram.notifications import TelegramNotifier
from config.logging import get_logger
from db.audit import record_audit_log, record_screenshot

logger = get_logger(__name__)


@dataclass
class ApplicationState:
    # Identity
    user_id: UUID = field(default_factory=uuid.uuid4)
    telegram_user_id: int = 0
    application_id: Optional[UUID] = None
    workflow_id: str = ""

    # Input
    job_url: str = ""

    # Parsed data
    job_title: str = ""
    company: str = ""
    platform: str = ""
    raw_jd: str = ""
    parsed_job: Optional[object] = None

    # Session
    session_loaded: bool = False
    is_logged_in: bool = False

    # Resume
    resume_pdf_path: Optional[str] = None

    # Form
    filled_fields: list = field(default_factory=list)

    # Validation
    validation_passed: bool = False
    validation_screenshot: str = ""
    validation_screenshot_bytes: Optional[bytes] = None

    # Result
    submitted: bool = False
    confirmation_id: Optional[str] = None
    error: Optional[str] = None

    # Flow control
    current_step: str = "start"
    requires_escalation: bool = False
    escalation_reason: str = ""


class OrchestratorAgent:
    """
    LangGraph-based multi-agent orchestrator.
    Builds and runs the full application workflow graph.
    """

    def __init__(
        self,
        ai_router: AIRouter,
        browser_manager: BrowserContextManager,
        notifier: TelegramNotifier,
    ):
        self.ai = ai_router
        self.browser_manager = browser_manager
        self.notifier = notifier

        # Instantiate all sub-agents
        self.memory = MemoryAgent()
        self.vision = VisionAgent(ai_router)
        self.job_parser = JobParserAgent(ai_router)
        self.browser_nav = BrowserNavAgent(self.vision)
        self.cred_store = CredentialStore()
        self.login_auth = LoginAuthAgent(self.vision, self.cred_store)
        self.resume_gen = ResumeGenerationAgent(ai_router, self.memory)
        self.escalation = EscalationAgent(notifier)
        self.form_filler = FormFillerAgent(ai_router, self.vision, self.memory)
        self.validation = ValidationAgent(self.vision)
        self.recovery = WorkflowRecoveryAgent()

        self._graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(dict)

        graph.add_node("navigate", self._node_navigate)
        graph.add_node("check_login", self._node_check_login)
        graph.add_node("parse_jd", self._node_parse_jd)
        graph.add_node("generate_resume", self._node_generate_resume)
        graph.add_node("fill_form", self._node_fill_form)
        graph.add_node("upload_resume", self._node_upload_resume)
        graph.add_node("validate", self._node_validate)
        graph.add_node("review_approval", self._node_review_approval)
        graph.add_node("submit", self._node_submit)
        graph.add_node("notify_success", self._node_notify_success)
        graph.add_node("handle_error", self._node_handle_error)

        graph.set_entry_point("navigate")

        graph.add_edge("navigate", "check_login")
        graph.add_conditional_edges(
            "check_login",
            lambda s: "parse_jd" if s.get("is_logged_in") else "handle_error",
        )
        graph.add_edge("parse_jd", "generate_resume")
        graph.add_edge("generate_resume", "fill_form")
        graph.add_edge("fill_form", "upload_resume")
        graph.add_edge("upload_resume", "validate")
        graph.add_conditional_edges(
            "validate",
            lambda s: "review_approval" if s.get("validation_passed") else "handle_error",
        )
        graph.add_edge("review_approval", "submit")
        graph.add_conditional_edges(
            "submit",
            lambda s: "notify_success" if s.get("submitted") else "handle_error",
        )
        graph.add_edge("notify_success", END)
        graph.add_edge("handle_error", END)

        return graph

    async def run(self, state: ApplicationState) -> ApplicationState:
        context, session_loaded = await self.browser_manager.load_session_context(
            state.user_id, state.platform or "custom"
        )
        state.session_loaded = session_loaded
        page = await context.new_page()

        try:
            state_dict = state.__dict__.copy()
            state_dict["_page"] = page
            state_dict["_context"] = context

            compiled = self._graph.compile()
            result = await compiled.ainvoke(state_dict)

            # Save session after workflow
            await self.browser_manager.save_session(
                state.user_id, state.platform or "custom", context
            )

            # Map result back to state
            for k, v in result.items():
                if not k.startswith("_") and hasattr(state, k):
                    setattr(state, k, v)
        except Exception as e:
            logger.error("orchestrator_error", error=str(e))
            state.error = str(e)
        finally:
            await page.close()
            await context.close()

        return state

    # ─── Nodes ────────────────────────────────────────────────────────────────

    async def _node_navigate(self, state: dict) -> dict:
        page = state["_page"]
        state["current_step"] = "navigate"
        await record_audit_log(
            state.get("application_id"),
            state.get("user_id"),
            "navigate_start",
            {"message": "Navigating to job posting", "job_url": state.get("job_url")},
        )
        await self.recovery.mark_running(state["application_id"])
        await self.browser_nav.navigate_to_url(page, state["job_url"])
        await self.browser_nav.handle_popup(page)

        # Detect platform
        platform = self.job_parser.detect_platform(state["job_url"])
        state["platform"] = platform

        # Smart-click apply button
        await self.browser_nav.smart_navigate_apply(page, state["user_id"])

        logger.info("navigated", url=state["job_url"], platform=platform)
        await record_audit_log(
            state.get("application_id"),
            state.get("user_id"),
            "navigate_complete",
            {"message": "Navigation complete", "platform": platform},
        )
        return state

    async def _node_check_login(self, state: dict) -> dict:
        page = state["_page"]
        state["current_step"] = "check_login"
        screenshot_bytes, _ = await capture_screenshot(page, "check_login", str(state["user_id"]))
        is_login = await self.vision.detect_login_page(screenshot_bytes)

        if is_login:
            logged_in = await self.login_auth.ensure_logged_in(
                page=page,
                platform=state["platform"],
                user_id=state["user_id"],
                telegram_user_id=state["telegram_user_id"],
                escalation_agent=self.escalation,
            )
            state["is_logged_in"] = logged_in
        else:
            state["is_logged_in"] = True

        await record_audit_log(
            state.get("application_id"),
            state.get("user_id"),
            "login_check_complete",
            {"message": "Login check completed", "logged_in": state.get("is_logged_in")},
        )
        return state

    async def _node_parse_jd(self, state: dict) -> dict:
        page = state["_page"]
        state["current_step"] = "parse_jd"
        raw_text = await self.browser_nav.extract_page_text(page)
        parsed = await self.job_parser.parse_job_description(raw_text, state["job_url"])

        state["raw_jd"] = raw_text
        state["parsed_job"] = parsed
        state["job_title"] = parsed.job_title
        state["company"] = parsed.company

        # Update application record
        async with __import__("db.database", fromlist=["get_db_session"]).get_db_session() as session:
            from db.repositories.applications import ApplicationsRepository
            repo = ApplicationsRepository(session)
            await repo.update_status(
                state["application_id"],
                status="running",
                job_title=parsed.job_title,
                company=parsed.company,
                platform=state["platform"],
            )

        logger.info("jd_parsed", title=parsed.job_title, company=parsed.company)
        await record_audit_log(
            state.get("application_id"),
            state.get("user_id"),
            "job_parsed",
            {
                "message": "Job description parsed",
                "job_title": parsed.job_title,
                "company": parsed.company,
                "platform": state.get("platform"),
            },
        )
        return state

    async def _node_generate_resume(self, state: dict) -> dict:
        state["current_step"] = "generate_resume"
        await record_audit_log(
            state.get("application_id"),
            state.get("user_id"),
            "resume_generation_start",
            {"message": "Generating tailored resume"},
        )
        parsed_job = state["parsed_job"]
        pdf_path = await self.resume_gen.generate_tailored_resume(
            user_id=state["user_id"],
            parsed_job=parsed_job,
            application_id=state["application_id"],
        )
        state["resume_pdf_path"] = pdf_path
        logger.info("resume_generated", path=pdf_path)
        await record_audit_log(
            state.get("application_id"),
            state.get("user_id"),
            "resume_generated",
            {"message": "Resume generated", "pdf_path": pdf_path},
        )
        return state

    async def _node_fill_form(self, state: dict) -> dict:
        page = state["_page"]
        state["current_step"] = "fill_form"
        filled = await self.form_filler.fill_all_visible_fields(
            page=page,
            user_id=state["user_id"],
            telegram_user_id=state["telegram_user_id"],
            escalation_agent=self.escalation,
        )
        state["filled_fields"] = filled
        logger.info("form_filled", fields_count=len(filled))
        await record_audit_log(
            state.get("application_id"),
            state.get("user_id"),
            "form_filled",
            {"message": "Form fields filled", "fields_filled": len(filled)},
        )
        return state

    async def _node_upload_resume(self, state: dict) -> dict:
        page = state["_page"]
        state["current_step"] = "upload_resume"
        pdf_path = state.get("resume_pdf_path")
        if pdf_path:
            uploaded = await self.browser_nav.handle_file_upload(
                page, pdf_path, label_text="Resume"
            )
            if not uploaded:
                # Try without label
                uploaded = await self.browser_nav.handle_file_upload(page, pdf_path)
            logger.info("resume_upload_attempted", uploaded=uploaded)
            await record_audit_log(
                state.get("application_id"),
                state.get("user_id"),
                "resume_upload",
                {
                    "message": "Resume upload attempted",
                    "uploaded": uploaded,
                    "pdf_path": pdf_path,
                },
            )
        return state

    async def _node_validate(self, state: dict) -> dict:
        page = state["_page"]
        state["current_step"] = "validate"
        result = await self.validation.validate_before_submit(
            page, state["user_id"]
        )
        state["validation_passed"] = result.passed
        state["validation_screenshot"] = result.screenshot_path
        state["validation_screenshot_bytes"] = result.screenshot_bytes
        await record_screenshot(
            state.get("application_id"),
            "pre_submit_validation",
            result.screenshot_path,
        )
        await record_audit_log(
            state.get("application_id"),
            state.get("user_id"),
            "validation_complete",
            {
                "message": "Validation complete",
                "passed": result.passed,
                "errors": result.errors,
                "missing_required": result.missing_required,
                "screenshot_path": result.screenshot_path,
            },
        )
        if not result.passed:
            state["error"] = f"Validation failed: {result.errors} missing: {result.missing_required}"
        return state

    async def _node_review_approval(self, state: dict) -> dict:
        state["current_step"] = "review_approval"
        screenshot_path = state.get("validation_screenshot", "")
        screenshot_bytes = state.get("validation_screenshot_bytes")
        if screenshot_bytes is None and screenshot_path:
            try:
                with open(screenshot_path, "rb") as f:
                    screenshot_bytes = f.read()
            except Exception:
                pass

        summary = (
            f"Job: *{state.get('job_title', 'Unknown')}* at *{state.get('company', 'Unknown')}*\n"
            f"Platform: {state.get('platform', 'unknown')}\n"
            f"Fields filled: {len(state.get('filled_fields', []))}\n"
            f"Resume: {'✓ uploaded' if state.get('resume_pdf_path') else '✗ not uploaded'}"
        )

        approved = await self.escalation.request_approval(
            telegram_user_id=state["telegram_user_id"],
            summary=summary,
            screenshot_bytes=screenshot_bytes,
        )

        if not approved:
            state["error"] = "User rejected submission"
            state["validation_passed"] = False
            await record_audit_log(
                state.get("application_id"),
                state.get("user_id"),
                "approval_rejected",
                {"message": "User rejected submission"},
            )
        else:
            await record_audit_log(
                state.get("application_id"),
                state.get("user_id"),
                "approval_granted",
                {
                    "message": "User approved submission",
                    "screenshot_path": screenshot_path,
                },
            )
        return state

    async def _node_submit(self, state: dict) -> dict:
        page = state["_page"]
        state["current_step"] = "submit"
        try:
            submit_selectors = [
                'button[type="submit"]',
                'button:has-text("Submit Application")',
                'button:has-text("Submit")',
                'button:has-text("Apply")',
                'input[type="submit"]',
            ]
            for sel in submit_selectors:
                try:
                    await page.click(sel, timeout=5000)
                    await page.wait_for_load_state("networkidle", timeout=15000)
                    break
                except Exception:
                    continue

            from browser.stealth import human_delay
            await human_delay(page, 1500, 2500)

            screenshot_bytes, screenshot_path = await capture_screenshot(page, "post_submit", str(state["user_id"]))
            await record_screenshot(
                state.get("application_id"),
                "post_submit",
                screenshot_path,
            )
            success = await self.vision.detect_success(screenshot_bytes)
            state["submitted"] = success
            await record_audit_log(
                state.get("application_id"),
                state.get("user_id"),
                "submission_checked",
                {
                    "message": "Submission confirmation checked",
                    "submitted": success,
                    "screenshot_path": screenshot_path,
                },
            )

            if success:
                # Try to grab confirmation text
                try:
                    body_text = await page.evaluate("document.body.innerText")
                    import re
                    match = re.search(r"(confirmation|reference|application)\s*(#|number|id)?:?\s*([A-Z0-9\-]{4,20})", body_text, re.IGNORECASE)
                    if match:
                        state["confirmation_id"] = match.group(3)
                except Exception:
                    pass

                await self.recovery.mark_completed(
                    state["application_id"],
                    state["user_id"],
                    state.get("confirmation_id"),
                )
            else:
                state["error"] = "Submission not confirmed by page"

        except Exception as e:
            state["error"] = str(e)
            state["submitted"] = False
            await record_audit_log(
                state.get("application_id"),
                state.get("user_id"),
                "submission_error",
                {"message": "Error during submission", "error": str(e)},
            )

        return state

    async def _node_notify_success(self, state: dict) -> dict:
        msg = (
            f"✅ *Application submitted successfully!*\n\n"
            f"🏢 Company: {state.get('company', 'Unknown')}\n"
            f"💼 Role: {state.get('job_title', 'Unknown')}\n"
            f"🔗 Platform: {state.get('platform', 'unknown')}\n"
        )
        if state.get("confirmation_id"):
            msg += f"🎫 Confirmation: `{state['confirmation_id']}`"
        await self.notifier.send_message(state["telegram_user_id"], msg)
        return state

    async def _node_handle_error(self, state: dict) -> dict:
        error = state.get("error", "Unknown error")
        logger.error("workflow_error", error=error, workflow_id=state.get("workflow_id"))

        if state.get("application_id"):
            await self.recovery.mark_failed(
                state["application_id"],
                state["user_id"],
                error,
                step=state.get("current_step", "unknown"),
            )
            await record_audit_log(
                state.get("application_id"),
                state.get("user_id"),
                "workflow_failed",
                {"message": "Workflow failed", "error": error, "step": state.get("current_step")},
            )

        await self.notifier.send_message(
            state["telegram_user_id"],
            f"❌ *Application failed*\n\n"
            f"Job: {state.get('job_title', state.get('job_url', 'Unknown'))}\n"
            f"Reason: {error[:300]}\n\n"
            f"Please try again or contact support."
        )
        return state
