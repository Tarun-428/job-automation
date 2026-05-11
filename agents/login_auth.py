from typing import Optional
from uuid import UUID

from playwright.async_api import BrowserContext, Page

from browser.stealth import human_delay, human_type
from browser.screenshot import capture_screenshot
from agents.vision import VisionAgent
from security.credential_store import CredentialStore
from config.logging import get_logger

logger = get_logger(__name__)


class LoginAuthAgent:
    def __init__(self, vision_agent: VisionAgent, credential_store: CredentialStore):
        self.vision = vision_agent
        self.cred_store = credential_store

    async def ensure_logged_in(
        self,
        page: Page,
        platform: str,
        user_id: UUID,
        telegram_user_id: int,
        escalation_agent=None,
    ) -> bool:
        """
        Check if logged in; attempt auto-login if not.
        Returns True if successfully authenticated.
        """
        screenshot_bytes, _ = await capture_screenshot(page, "login_check", str(user_id))
        is_login = await self.vision.detect_login_page(screenshot_bytes)

        if not is_login:
            logger.info("already_logged_in", platform=platform)
            return True

        logger.info("login_required", platform=platform)

        # Try stored credentials
        creds = await self.cred_store.load(user_id, platform)
        if creds:
            username, password = creds
            success = await self._attempt_login(page, platform, username, password, user_id)
            if success:
                return True

        # Escalate to user for credentials
        if escalation_agent:
            await escalation_agent.notifier.send_message(
                telegram_user_id,
                f"🔐 Login required for *{platform}*.\n\nPlease enter your credentials in format:\n`email@example.com password123`"
            )
            response = await escalation_agent.ask_question(
                telegram_user_id,
                f"Enter your {platform} credentials (email password):",
                context="Separated by a space",
            )
            if response:
                parts = response.strip().split(" ", 1)
                if len(parts) == 2:
                    username, password = parts
                    await self.cred_store.save(user_id, platform, username, password)
                    success = await self._attempt_login(page, platform, username, password, user_id)
                    if success:
                        return True

        logger.error("login_failed", platform=platform)
        return False

    async def _attempt_login(
        self,
        page: Page,
        platform: str,
        username: str,
        password: str,
        user_id: UUID,
    ) -> bool:
        try:
            await human_delay(page, 500, 1000)
            # Try common email selectors
            email_selectors = [
                'input[type="email"]',
                'input[name="email"]',
                'input[name="username"]',
                'input[id*="email"]',
                'input[placeholder*="email" i]',
            ]
            email_filled = False
            for sel in email_selectors:
                try:
                    await page.fill(sel, username, timeout=3000)
                    email_filled = True
                    break
                except Exception:
                    continue

            if not email_filled:
                return False

            await human_delay(page, 300, 700)

            password_selectors = [
                'input[type="password"]',
                'input[name="password"]',
                'input[id*="password"]',
            ]
            pass_filled = False
            for sel in password_selectors:
                try:
                    await page.fill(sel, password, timeout=3000)
                    pass_filled = True
                    break
                except Exception:
                    continue

            if not pass_filled:
                return False

            await human_delay(page, 300, 700)

            # Click submit button
            submit_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Sign in")',
                'button:has-text("Log in")',
                'button:has-text("Login")',
                'button:has-text("Continue")',
            ]
            for sel in submit_selectors:
                try:
                    await page.click(sel, timeout=3000)
                    break
                except Exception:
                    continue

            await page.wait_for_load_state("networkidle", timeout=10000)
            await human_delay(page, 1000, 2000)

            # Verify login succeeded
            screenshot_bytes, _ = await capture_screenshot(page, "post_login", str(user_id))
            still_login = await self.vision.detect_login_page(screenshot_bytes)
            return not still_login

        except Exception as e:
            logger.error("login_attempt_error", error=str(e), platform=platform)
            return False
