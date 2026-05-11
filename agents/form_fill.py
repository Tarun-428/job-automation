import json
import re
from typing import Optional, List
from uuid import UUID

from playwright.async_api import Page

from ai.router import AIRouter
from ai.prompts.form_fill import FORM_FILL_SYSTEM, build_form_fill_prompt
from ai.confidence import classify_question, needs_escalation, extract_confidence_from_text
from agents.vision import VisionAgent
from agents.memory import MemoryAgent
from browser.screenshot import capture_screenshot
from browser.stealth import human_delay, human_type
from config.settings import get_settings
from config.logging import get_logger

logger = get_logger(__name__)


class FormFillerAgent:
    def __init__(
        self,
        ai_router: AIRouter,
        vision_agent: VisionAgent,
        memory_agent: MemoryAgent,
    ):
        self.ai = ai_router
        self.vision = vision_agent
        self.memory = memory_agent
        self.settings = get_settings()

    async def fill_all_visible_fields(
        self,
        page: Page,
        user_id: UUID,
        telegram_user_id: int,
        escalation_agent=None,
    ) -> List[dict]:
        """
        Identify all form fields via DOM + vision and fill them intelligently.
        Returns list of filled field records.
        """
        profile = await self.memory.get_profile(user_id)
        if not profile:
            logger.warning("no_profile_found", user_id=str(user_id))
            return []

        screenshot_bytes, _ = await capture_screenshot(page, "form_scan", str(user_id))
        analysis = await self.vision.analyze_page(screenshot_bytes, "fill out all form fields")

        filled_records = []

        # Process AI-identified fields
        for field in analysis.fields:
            field_name = field.get("name", "")
            field_type = field.get("type", "text")
            placeholder = field.get("placeholder", "")
            question_text = field_name or placeholder or field.get("selector_hint", "")

            if not question_text:
                continue

            # Check answer history first
            prev = await self.memory.get_previous_answer(user_id, question_text)
            if prev and prev["confidence"] >= self.settings.ai_confidence_threshold:
                answer = prev["answer"]
                confidence = prev["confidence"]
            else:
                # Ask AI for answer
                ai_resp = await self._get_ai_answer(question_text, field_type, profile)
                answer = ai_resp.get("answer", "")
                confidence = ai_resp.get("confidence", 0.0)

            classification = classify_question(question_text, answer, confidence)

            # Escalate risky/impossible questions
            if needs_escalation(classification, confidence, self.settings.ai_confidence_threshold):
                if escalation_agent:
                    user_answer = await escalation_agent.ask_question(
                        telegram_user_id,
                        question_text,
                        context=f"Application form question (type: {field_type})",
                        screenshot_bytes=screenshot_bytes,
                    )
                    if user_answer:
                        answer = self._normalize_user_input(user_answer)
                        confidence = 0.95
                        classification = "deterministic"
                    else:
                        logger.warning("escalation_no_response", question=question_text)
                        continue

            # Fill the field
            if answer:
                filled = await self._fill_field(page, field, answer, field_type)
                if filled:
                    await self.memory.save_answer(user_id, question_text, answer, confidence)
                    filled_records.append({
                        "question": question_text,
                        "answer": answer,
                        "confidence": confidence,
                        "classification": classification,
                    })

        # Also scan DOM directly for any missed fields
        dom_records = await self._fill_dom_fields(page, profile, user_id)
        filled_records.extend(dom_records)

        return filled_records

    async def _get_ai_answer(self, question: str, field_type: str, profile: dict) -> dict:
        prompt = build_form_fill_prompt(question, field_type, profile)
        result = await self.ai.generate(prompt, system=FORM_FILL_SYSTEM)
        if not result.success:
            return {"answer": "", "confidence": 0.0}
        try:
            match = re.search(r"\{.*?\}", result.text, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception:
            pass
        return {"answer": result.text.strip(), "confidence": 0.5}

    async def _fill_field(self, page: Page, field: dict, answer: str, field_type: str) -> bool:
        selector_hint = field.get("selector_hint", "")
        field_name = field.get("name", "")

        selectors_to_try = []
        if selector_hint:
            selectors_to_try.append(selector_hint)
        if field_name:
            selectors_to_try.extend([
                f'input[name="{field_name}"]',
                f'textarea[name="{field_name}"]',
                f'select[name="{field_name}"]',
                f'input[id="{field_name}"]',
                f'[data-testid="{field_name}"]',
            ])

        for sel in selectors_to_try:
            try:
                el = await page.query_selector(sel)
                if not el:
                    continue

                tag = await el.evaluate("el => el.tagName.toLowerCase()")

                if tag == "select" or field_type == "select":
                    await el.select_option(label=answer)
                elif field_type in ("radio", "checkbox"):
                    await el.check()
                elif tag in ("input", "textarea"):
                    await el.fill("")
                    await el.type(answer, delay=60)
                else:
                    await el.fill(answer)

                await human_delay(page, 200, 500)
                return True
            except Exception as e:
                logger.debug("field_fill_selector_failed", selector=sel, error=str(e))
                continue
        return False

    async def _fill_dom_fields(self, page: Page, profile: dict, user_id: UUID) -> list:
        """Directly scan DOM for common field patterns and fill them."""
        filled = []
        field_mappings = {
            'input[name*="first" i][type="text"]': profile.get("full_name", "").split()[0] if profile.get("full_name") else "",
            'input[name*="last" i][type="text"]': profile.get("full_name", "").split()[-1] if profile.get("full_name") else "",
            'input[name*="email" i], input[type="email"]': profile.get("email", ""),
            'input[name*="phone" i], input[type="tel"]': profile.get("phone", ""),
            'input[name*="linkedin" i]': profile.get("linkedin_url", ""),
            'input[name*="github" i]': profile.get("github_url", ""),
            'input[name*="portfolio" i], input[name*="website" i]': profile.get("portfolio_url", ""),
            'input[name*="city" i], input[name*="location" i]': profile.get("location", ""),
        }
        for selector, value in field_mappings.items():
            if not value:
                continue
            try:
                elements = await page.query_selector_all(selector)
                for el in elements:
                    visible = await el.is_visible()
                    if visible:
                        await el.fill("")
                        await el.type(str(value), delay=50)
                        await human_delay(page, 100, 300)
                        filled.append({"selector": selector, "value": value})
                        break
            except Exception:
                continue
        return filled

    @staticmethod
    def _normalize_user_input(text: str) -> str:
        """Infer and clean user-provided answers."""
        normalized = text.strip()
        # Common typo corrections
        replacements = {
            "immedite": "Immediate",
            "imediate": "Immediate",
            "immidiate": "Immediate",
            "immeadiate": "Immediate",
        }
        lower = normalized.lower()
        for typo, correct in replacements.items():
            if typo in lower:
                return correct
        return normalized
