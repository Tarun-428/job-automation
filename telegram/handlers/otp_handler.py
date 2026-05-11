import re
from typing import Optional

import redis.asyncio as aioredis

from config.settings import get_settings
from config.logging import get_logger

logger = get_logger(__name__)

OTP_RE = re.compile(r"\b\d{4,8}\b")


class OTPHandler:
    def __init__(self):
        self.settings = get_settings()

    async def handle(self, telegram_user_id: int, text: str) -> bool:
        """
        If message looks like an OTP, store it in Redis for the escalation agent.
        Returns True if handled.
        """
        match = OTP_RE.search(text.strip())
        if not match:
            return False

        otp = match.group(0)
        r = await aioredis.from_url(self.settings.redis_url)

        # Store under a key the escalation agent polls
        key = f"escalation:response:{telegram_user_id}:otp"
        await r.set(key, otp, ex=300)
        logger.info("otp_stored", user=telegram_user_id)
        return True
