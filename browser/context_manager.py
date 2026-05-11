import json
import os
from typing import Optional
from uuid import UUID

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Playwright,
)

from browser.stealth import apply_stealth, set_human_like_viewport
from config.settings import get_settings
from config.logging import get_logger
from security.session_encrypt import encrypt_storage_state, decrypt_storage_state
from db.database import get_db_session
from db.repositories.sessions import SessionsRepository

logger = get_logger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


class BrowserContextManager:
    """Manages isolated Playwright browser contexts per user."""

    def __init__(self):
        self.settings = get_settings()
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.settings.browser_headless,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--window-size=1366,768",
            ],
        )
        logger.info("browser_started")

    async def stop(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("browser_stopped")

    async def create_context(
        self,
        user_id: UUID,
        platform: str,
        storage_state_json: Optional[str] = None,
    ) -> BrowserContext:
        import random
        ua = random.choice(USER_AGENTS)

        context_kwargs = {
            "user_agent": ua,
            "viewport": {"width": 1366, "height": 768},
            "locale": "en-US",
            "timezone_id": "America/New_York",
            "ignore_https_errors": True,
        }
        if storage_state_json:
            try:
                state = json.loads(storage_state_json)
                context_kwargs["storage_state"] = state
            except json.JSONDecodeError:
                logger.warning("invalid_storage_state", user_id=str(user_id), platform=platform)

        context = await self._browser.new_context(**context_kwargs)
        if self.settings.browser_stealth:
            await apply_stealth(context)
        return context

    async def load_session_context(
        self, user_id: UUID, platform: str
    ) -> tuple[BrowserContext, bool]:
        """
        Load existing session if valid, else create a fresh context.
        Returns (context, session_was_loaded).
        """
        async with get_db_session() as session:
            repo = SessionsRepository(session)
            browser_session = await repo.get_valid_session(user_id, platform)

        if browser_session and browser_session.storage_state:
            try:
                decrypted = decrypt_storage_state(browser_session.storage_state)
                context = await self.create_context(user_id, platform, decrypted)
                logger.info("session_loaded", user_id=str(user_id), platform=platform)
                return context, True
            except Exception as e:
                logger.warning("session_load_failed", error=str(e))

        context = await self.create_context(user_id, platform)
        return context, False

    async def save_session(
        self, user_id: UUID, platform: str, context: BrowserContext
    ) -> None:
        try:
            state = await context.storage_state()
            state_json = json.dumps(state)
            encrypted = encrypt_storage_state(state_json)
            async with get_db_session() as session:
                repo = SessionsRepository(session)
                await repo.upsert_session(
                    user_id=user_id,
                    platform=platform,
                    storage_state=encrypted,
                )
            logger.info("session_saved", user_id=str(user_id), platform=platform)
        except Exception as e:
            logger.error("session_save_failed", error=str(e))


# Singleton
_manager: Optional[BrowserContextManager] = None


def get_browser_manager() -> BrowserContextManager:
    global _manager
    if _manager is None:
        _manager = BrowserContextManager()
    return _manager
