from typing import Optional
import httpx

from config.settings import get_settings
from config.logging import get_logger

logger = get_logger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}"


class TelegramNotifier:
    def __init__(self):
        settings = get_settings()
        self.token = settings.telegram_bot_token
        self.base = f"https://api.telegram.org/bot{self.token}"

    async def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str = "Markdown",
        reply_markup: Optional[dict] = None,
    ) -> bool:
        payload: dict = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(f"{self.base}/sendMessage", json=payload)
                r.raise_for_status()
                return True
        except Exception as e:
            logger.error("telegram_send_failed", error=str(e), chat_id=chat_id)
            return False

    async def send_photo(
        self,
        chat_id: int,
        image_bytes: bytes,
        caption: str = "",
    ) -> bool:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                files = {"photo": ("screenshot.png", image_bytes, "image/png")}
                data = {"chat_id": str(chat_id), "caption": caption, "parse_mode": "Markdown"}
                r = await client.post(f"{self.base}/sendPhoto", data=data, files=files)
                r.raise_for_status()
                return True
        except Exception as e:
            logger.error("telegram_photo_failed", error=str(e))
            return False

    async def send_document(
        self,
        chat_id: int,
        file_bytes: bytes,
        filename: str,
        caption: str = "",
    ) -> bool:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                files = {"document": (filename, file_bytes, "application/pdf")}
                data = {"chat_id": str(chat_id), "caption": caption}
                r = await client.post(f"{self.base}/sendDocument", data=data, files=files)
                r.raise_for_status()
                return True
        except Exception as e:
            logger.error("telegram_document_failed", error=str(e))
            return False

    async def send_typing(self, chat_id: int) -> None:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(
                    f"{self.base}/sendChatAction",
                    json={"chat_id": chat_id, "action": "typing"},
                )
        except Exception:
            pass
