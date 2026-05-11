import json
import re
from typing import Optional
from uuid import UUID

from playwright.async_api import BrowserContext, Page

from browser.screenshot import capture_screenshot
from browser.stealth import human_delay
from agents.vision import VisionAgent
from config.logging import get_logger

logger = get_logger(__name__)


class BrowserNavAgent:
    def __init__(self, vision_agent: VisionAgent):
        self.vision = vision_agent

    async def navigate_to_url(self, page: Page, url: str) -> None:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_load_state("networkidle", timeout=15000)
        await human_delay(page, 800, 1500)

    async def extract_page_text(self, page: Page) -> str:
        """Extract visible text from the page for JD parsing."""
        try:
            text = await page.evaluate("""() => {
                const body = document.body;
                const clone = body.cloneNode(true);
                // Remove script and style elements
                clone.querySelectorAll('script, style, nav, footer, header').forEach(e => e.remove());
                return clone.innerText || clone.textContent || '';
            }""")
            return text[:8000]  # Limit to 8k chars
        except Exception as e:
            logger.warning("text_extract_failed", error=str(e))
            return ""

    async def find_and_click(
        self,
        page: Page,
        target_text: str,
        user_id: UUID,
    ) -> bool:
        """Find a button/link by text and click it."""
        selectors = [
            f'button:has-text("{target_text}")',
            f'a:has-text("{target_text}")',
            f'[role="button"]:has-text("{target_text}")',
            f'input[value="{target_text}"]',
        ]
        for sel in selectors:
            try:
                await page.click(sel, timeout=5000)
                await human_delay(page, 500, 1200)
                await page.wait_for_load_state("networkidle", timeout=10000)
                return True
            except Exception:
                continue
        return False

    async def smart_navigate_apply(
        self,
        page: Page,
        user_id: UUID,
        goal: str = "find and click the apply button",
    ) -> bool:
        """
        Use AI vision to determine and execute the best navigation action.
        Prefers 'Continue to Apply' over 'Complete Profile' etc.
        """
        screenshot_bytes, _ = await capture_screenshot(page, "nav_decision", str(user_id))
        analysis = await self.vision.analyze_page(screenshot_bytes, goal)

        if not analysis.buttons:
            logger.warning("no_buttons_found")
            return False

        # Prioritize buttons that advance application
        priority_phrases = [
            "continue to apply", "apply now", "apply", "start application",
            "begin application", "proceed", "next", "continue",
        ]
        # Deprioritize profile/setup buttons
        skip_phrases = [
            "complete profile", "update profile", "add skills", "edit",
        ]

        # Find recommended button from AI
        for btn in analysis.buttons:
            btn_text = btn.get("text", "").lower()
            if btn.get("recommended"):
                if not any(skip in btn_text for skip in skip_phrases):
                    clicked = await self.find_and_click(page, btn.get("text", ""), user_id)
                    if clicked:
                        return True

        # Fallback: try priority phrases
        for phrase in priority_phrases:
            clicked = await self.find_and_click(page, phrase.title(), user_id)
            if clicked:
                return True

        return False

    async def scroll_to_bottom(self, page: Page) -> None:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await human_delay(page, 500, 1000)

    async def handle_popup(self, page: Page) -> None:
        """Dismiss common popups/modals."""
        dismiss_selectors = [
            '[aria-label="Close"]',
            '[aria-label="Dismiss"]',
            'button:has-text("Not now")',
            'button:has-text("Close")',
            'button:has-text("Maybe later")',
            'button:has-text("Skip")',
        ]
        for sel in dismiss_selectors:
            try:
                el = await page.query_selector(sel)
                if el:
                    await el.click(timeout=2000)
                    await human_delay(page, 300, 600)
                    return
            except Exception:
                continue

    async def handle_file_upload(
        self,
        page: Page,
        file_path: str,
        label_text: Optional[str] = None,
    ) -> bool:
        """Upload a file to a file input."""
        try:
            file_selectors = ['input[type="file"]']
            if label_text:
                file_selectors.insert(0, f'label:has-text("{label_text}") input[type="file"]')

            for sel in file_selectors:
                try:
                    file_input = await page.query_selector(sel)
                    if file_input:
                        await file_input.set_input_files(file_path)
                        await human_delay(page, 500, 1000)
                        return True
                except Exception:
                    continue
        except Exception as e:
            logger.error("file_upload_error", error=str(e))
        return False
