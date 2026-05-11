import re
import redis.asyncio as aioredis

from config.settings import get_settings
from config.logging import get_logger

logger = get_logger(__name__)

ESCALATION_ID_RE = re.compile(r"ID:\s*`?([a-f0-9]{12})`?", re.IGNORECASE)


class ApprovalHandler:
    def __init__(self):
        self.settings = get_settings()

    async def handle(self, telegram_user_id: int, text: str) -> bool:
        """
        Store user response for escalation agent polling.
        Tries to extract escalation ID from context; falls back to generic key.
        Returns True if a response was stored.
        """
        r = await aioredis.from_url(self.settings.redis_url)

        # Look for escalation ID in previous messages or current text
        match = ESCALATION_ID_RE.search(text)
        escalation_id = match.group(1) if match else None

        if escalation_id:
            key = f"escalation:response:{telegram_user_id}:{escalation_id}"
            await r.set(key, text.strip(), ex=600)
            logger.info("approval_stored", user=telegram_user_id, esc_id=escalation_id)
            return True

        # Generic: store as latest response for this user
        key = f"escalation:latest:{telegram_user_id}"
        await r.set(key, text.strip(), ex=600)
        return True
