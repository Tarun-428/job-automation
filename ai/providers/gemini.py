import base64
from typing import Optional
import httpx
from config.settings import get_settings
from config.logging import get_logger

logger = get_logger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider:
    def __init__(self):
        settings = get_settings()
        self.api_key = settings.gemini_api_key
        self.model = "gemini-1.5-flash"

    async def generate_text(self, prompt: str, system: Optional[str] = None) -> dict:
        parts = []
        if system:
            parts.append({"text": f"[SYSTEM]: {system}\n\n"})
        parts.append({"text": prompt})
        return await self._generate(parts)

    async def analyze_screenshot(
        self, prompt: str, image_bytes: bytes, system: Optional[str] = None
    ) -> dict:
        image_b64 = base64.b64encode(image_bytes).decode()
        parts = []
        if system:
            parts.append({"text": f"[SYSTEM]: {system}\n\n"})
        parts.append({"text": prompt})
        parts.append({
            "inline_data": {
                "mime_type": "image/png",
                "data": image_b64,
            }
        })
        return await self._generate(parts)

    async def _generate(self, parts: list) -> dict:
        url = f"{GEMINI_API_BASE}/models/{self.model}:generateContent?key={self.api_key}"
        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 4096,
            },
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(url, json=payload)
                r.raise_for_status()
                data = r.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                return {"success": True, "text": text, "raw": data}
        except httpx.TimeoutException:
            return {"success": False, "error": "timeout", "text": ""}
        except Exception as e:
            logger.error("gemini_error", error=str(e))
            return {"success": False, "error": str(e), "text": ""}
