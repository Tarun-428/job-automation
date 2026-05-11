import json
import re
from typing import Optional
from dataclasses import dataclass, field

from ai.router import AIRouter
from ai.prompts.form_fill import SCREENSHOT_ANALYSIS_SYSTEM, build_screenshot_analysis_prompt
from config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PageAnalysis:
    page_state: str = "unknown"
    fields: list = field(default_factory=list)
    buttons: list = field(default_factory=list)
    next_action: dict = field(default_factory=dict)
    confidence: float = 0.0
    raw_text: str = ""


class VisionAgent:
    def __init__(self, ai_router: AIRouter):
        self.ai = ai_router

    async def analyze_page(
        self, screenshot_bytes: bytes, goal: str
    ) -> PageAnalysis:
        prompt = build_screenshot_analysis_prompt(goal)
        result = await self.ai.analyze_screenshot(
            prompt, screenshot_bytes, system=SCREENSHOT_ANALYSIS_SYSTEM
        )
        if not result.success:
            logger.warning("vision_failed", goal=goal, error=result.error)
            return PageAnalysis(confidence=0.0)

        return self._parse_analysis(result.text)

    def _parse_analysis(self, text: str) -> PageAnalysis:
        try:
            json_match = re.search(r"\{.*\}", text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return PageAnalysis(
                    page_state=data.get("page_state", "unknown"),
                    fields=data.get("fields", []),
                    buttons=data.get("buttons", []),
                    next_action=data.get("next_action", {}),
                    confidence=float(data.get("confidence", 0.5)),
                    raw_text=text,
                )
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning("vision_parse_error", error=str(e))
        return PageAnalysis(confidence=0.3, raw_text=text)

    async def detect_captcha(self, screenshot_bytes: bytes) -> bool:
        prompt = """Look at this screenshot. Is there a CAPTCHA visible?
        Return JSON: {"captcha_detected": true/false, "captcha_type": "recaptcha|hcaptcha|image|text|none"}"""
        result = await self.ai.analyze_screenshot(prompt, screenshot_bytes)
        if result.success:
            try:
                match = re.search(r"\{.*?\}", result.text, re.DOTALL)
                if match:
                    data = json.loads(match.group())
                    return bool(data.get("captcha_detected", False))
            except Exception:
                pass
        return False

    async def detect_login_page(self, screenshot_bytes: bytes) -> bool:
        prompt = """Is this a login/signin page? Look for email/username and password fields.
        Return JSON: {"is_login_page": true/false}"""
        result = await self.ai.analyze_screenshot(prompt, screenshot_bytes)
        if result.success:
            try:
                match = re.search(r"\{.*?\}", result.text, re.DOTALL)
                if match:
                    data = json.loads(match.group())
                    return bool(data.get("is_login_page", False))
            except Exception:
                pass
        return False

    async def detect_success(self, screenshot_bytes: bytes) -> bool:
        prompt = """Has the job application been successfully submitted?
        Look for success messages, confirmation numbers, or thank-you pages.
        Return JSON: {"submission_success": true/false, "confirmation_text": "..."}"""
        result = await self.ai.analyze_screenshot(prompt, screenshot_bytes)
        if result.success:
            try:
                match = re.search(r"\{.*?\}", result.text, re.DOTALL)
                if match:
                    data = json.loads(match.group())
                    return bool(data.get("submission_success", False))
            except Exception:
                pass
        return False
