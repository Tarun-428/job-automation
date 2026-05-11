import redis.asyncio as aioredis

from config.settings import get_settings
from config.logging import get_logger

logger = get_logger(__name__)


class QuestionHandler:
    """Handles free-text answers from users during escalation flows."""

    def __init__(self):
        self.settings = get_settings()

    async def route_response(self, telegram_user_id: int, text: str, escalation_id: str) -> None:
        """Store a user response for a specific escalation ID."""
        r = await aioredis.from_url(self.settings.redis_url)
        key = f"escalation:response:{telegram_user_id}:{escalation_id}"
        await r.set(key, text.strip(), ex=600)
        logger.info("question_response_stored", user=telegram_user_id, esc_id=escalation_id)
