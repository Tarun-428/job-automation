import asyncio
from typing import Optional
from uuid import UUID

import redis.asyncio as aioredis

from config.settings import get_settings
from config.logging import get_logger
from telegram.notifications import TelegramNotifier

logger = get_logger(__name__)

ESCALATION_TIMEOUT = 300  # 5 minutes


class EscalationAgent:
    """
    Handles human-in-the-loop escalation via Telegram.
    Uses Redis pub/sub to wait for user responses.
    """

    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier
        self.settings = get_settings()
        self._redis: Optional[aioredis.Redis] = None

    async def _get_redis(self) -> aioredis.Redis:
        if not self._redis:
            self._redis = await aioredis.from_url(self.settings.redis_url)
        return self._redis

    def _response_key(self, telegram_user_id: int, escalation_id: str) -> str:
        return f"escalation:response:{telegram_user_id}:{escalation_id}"

    async def ask_question(
        self,
        telegram_user_id: int,
        question: str,
        context: Optional[str] = None,
        escalation_id: Optional[str] = None,
        screenshot_bytes: Optional[bytes] = None,
    ) -> Optional[str]:
        """
        Send question to user via Telegram and wait for response.
        Returns user's answer or None on timeout.
        """
        import uuid as _uuid
        if not escalation_id:
            escalation_id = _uuid.uuid4().hex[:12]

        message = f"🤔 *Question for you:*\n\n{question}"
        if context:
            message += f"\n\n_Context: {context}_"
        message += f"\n\n_Reply to continue your application. (ID: `{escalation_id}`)_"

        if screenshot_bytes:
            await self.notifier.send_photo(
                telegram_user_id, screenshot_bytes,
                caption=f"Application question needs your input\n\nID: `{escalation_id}`"
            )

        await self.notifier.send_message(telegram_user_id, message)

        # Wait for response via Redis
        redis = await self._get_redis()
        response_key = self._response_key(telegram_user_id, escalation_id)

        # Poll with timeout
        for _ in range(ESCALATION_TIMEOUT):
            value = await redis.get(response_key)
            if value:
                await redis.delete(response_key)
                response = value.decode()
                logger.info(
                    "escalation_answered",
                    user_id=telegram_user_id,
                    escalation_id=escalation_id,
                )
                return response
            await asyncio.sleep(1)

        logger.warning(
            "escalation_timeout",
            user_id=telegram_user_id,
            escalation_id=escalation_id,
        )
        return None

    async def store_user_response(
        self, telegram_user_id: int, escalation_id: str, response: str
    ) -> None:
        """Called by Telegram handler when user replies."""
        redis = await self._get_redis()
        key = self._response_key(telegram_user_id, escalation_id)
        await redis.set(key, response, ex=600)

    async def request_otp(self, telegram_user_id: int, platform: str) -> Optional[str]:
        return await self.ask_question(
            telegram_user_id,
            f"🔐 OTP required for *{platform}*.\nPlease enter the OTP you received:",
            context="Login verification step",
        )

    async def request_captcha_solve(
        self,
        telegram_user_id: int,
        screenshot_bytes: bytes,
        platform: str,
    ) -> Optional[str]:
        return await self.ask_question(
            telegram_user_id,
            f"🤖 CAPTCHA detected on *{platform}*.\n\nPlease solve the CAPTCHA and reply `done` when complete.",
            screenshot_bytes=screenshot_bytes,
        )

    async def request_approval(
        self,
        telegram_user_id: int,
        summary: str,
        screenshot_bytes: Optional[bytes] = None,
    ) -> bool:
        response = await self.ask_question(
            telegram_user_id,
            f"✅ Ready to submit application.\n\n{summary}\n\nReply `yes` to submit or `no` to cancel.",
            screenshot_bytes=screenshot_bytes,
        )
        if response and response.strip().lower() in ("yes", "y", "submit", "ok", "confirm"):
            return True
        return False
