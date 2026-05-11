import json
import re
from dataclasses import dataclass, field
from typing import List, Optional
from uuid import UUID

from playwright.async_api import Page

from agents.vision import VisionAgent
from browser.screenshot import capture_screenshot
from config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ValidationResult:
    passed: bool = True
    missing_required: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    resume_uploaded: bool = False
    screenshot_path: str = ""
    screenshot_bytes: Optional[bytes] = None


class ValidationAgent:
    def __init__(self, vision_agent: VisionAgent):
        self.vision = vision_agent

    async def validate_before_submit(
        self, page: Page, user_id: UUID
    ) -> ValidationResult:
        result = ValidationResult()

        screenshot_bytes, path = await capture_screenshot(
            page, "pre_submit_validation", str(user_id)
        )
        result.screenshot_path = path
        result.screenshot_bytes = screenshot_bytes

        # Check for visible validation errors
        error_selectors = [
            ".error", ".field-error", "[aria-invalid='true']",
            ".invalid-feedback", ".has-error",
        ]
        for sel in error_selectors:
            try:
                elements = await page.query_selector_all(sel)
                for el in elements:
                    visible = await el.is_visible()
                    if visible:
                        text = await el.text_content()
                        if text and text.strip():
                            result.errors.append(text.strip())
                            result.passed = False
            except Exception:
                continue

        # Check required fields are filled
        required_selectors = [
            "input[required]:not([type='hidden'])",
            "textarea[required]",
            "select[required]",
        ]
        for sel in required_selectors:
            try:
                elements = await page.query_selector_all(sel)
                for el in elements:
                    visible = await el.is_visible()
                    if not visible:
                        continue
                    value = await el.input_value()
                    if not value or not value.strip():
                        label = await self._get_field_label(page, el)
                        result.missing_required.append(label or sel)
                        result.passed = False
            except Exception:
                continue

        # Check resume upload
        try:
            file_inputs = await page.query_selector_all('input[type="file"]')
            for fi in file_inputs:
                # If a file input has been activated, it usually has a sibling label
                parent_text = await fi.evaluate(
                    "el => el.parentElement ? el.parentElement.innerText : ''"
                )
                if "resume" in parent_text.lower() or "cv" in parent_text.lower():
                    result.resume_uploaded = True
        except Exception:
            pass

        # Use AI vision to double-check page state
        analysis = await self.vision.analyze_page(
            screenshot_bytes, "check if form is complete and ready to submit"
        )
        if analysis.page_state in ("error",):
            result.passed = False
            result.errors.append("Page shows error state")

        logger.info(
            "validation_complete",
            passed=result.passed,
            missing=result.missing_required,
            errors=result.errors,
        )
        return result

    async def _get_field_label(self, page: Page, element) -> str:
        try:
            field_id = await element.get_attribute("id")
            if field_id:
                label_el = await page.query_selector(f'label[for="{field_id}"]')
                if label_el:
                    return await label_el.text_content() or ""
            placeholder = await element.get_attribute("placeholder")
            if placeholder:
                return placeholder
            name = await element.get_attribute("name")
            return name or "unknown field"
        except Exception:
            return "unknown field"
