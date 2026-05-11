import base64
from typing import Optional
import httpx
from config.settings import get_settings
from config.logging import get_logger

logger = get_logger(__name__)


class AnthropicProvider:
    def __init__(self):
        settings = get_settings()
        self.api_key = settings.anthropic_api_key
        self.model = "claude-sonnet-4-5"
        self.base_url = "https://api.anthropic.com/v1"

    async def generate_text(self, prompt: str, system: Optional[str] = None) -> dict:
        messages = [{"role": "user", "content": prompt}]
        return await self._generate(messages, system)

    async def analyze_screenshot(
        self, prompt: str, image_bytes: bytes, system: Optional[str] = None
    ) -> dict:
        image_b64 = base64.b64encode(image_bytes).decode()
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ]
        return await self._generate(messages, system)

    async def _generate(self, messages: list, system: Optional[str]) -> dict:
        payload: dict = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": messages,
        }
        if system:
            payload["system"] = system
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(f"{self.base_url}/messages", json=payload, headers=headers)
                r.raise_for_status()
                data = r.json()
                text = data["content"][0]["text"]
                return {"success": True, "text": text, "raw": data}
        except httpx.TimeoutException:
            return {"success": False, "error": "timeout", "text": ""}
        except Exception as e:
            logger.error("anthropic_error", error=str(e))
            return {"success": False, "error": str(e), "text": ""}
