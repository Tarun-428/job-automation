from typing import Optional
import httpx
from config.settings import get_settings
from config.logging import get_logger

logger = get_logger(__name__)


class GroqProvider:
    def __init__(self):
        settings = get_settings()
        self.api_key = settings.groq_api_key
        self.model = "llama-3.1-70b-versatile"
        self.base_url = "https://api.groq.com/openai/v1"

    async def generate_text(self, prompt: str, system: Optional[str] = None) -> dict:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 4096,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
                r.raise_for_status()
                data = r.json()
                text = data["choices"][0]["message"]["content"]
                return {"success": True, "text": text, "raw": data}
        except httpx.TimeoutException:
            return {"success": False, "error": "timeout", "text": ""}
        except Exception as e:
            logger.error("groq_error", error=str(e))
            return {"success": False, "error": str(e), "text": ""}

    async def analyze_screenshot(self, prompt: str, image_bytes: bytes, system: Optional[str] = None) -> dict:
        # Groq does not support vision natively; return failure to trigger next fallback
        return {"success": False, "error": "vision_not_supported", "text": ""}
