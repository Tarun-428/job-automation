from typing import Optional
import httpx
from config.settings import get_settings
from config.logging import get_logger

logger = get_logger(__name__)


class OpenRouterProvider:
    def __init__(self):
        settings = get_settings()
        self.api_key = settings.openrouter_api_key
        self.model = "meta-llama/llama-3.1-70b-instruct"
        self.base_url = "https://openrouter.ai/api/v1"

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
            "HTTP-Referer": "https://jobbot.ai",
        }
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
                r.raise_for_status()
                data = r.json()
                text = data["choices"][0]["message"]["content"]
                return {"success": True, "text": text, "raw": data}
        except httpx.TimeoutException:
            return {"success": False, "error": "timeout", "text": ""}
        except Exception as e:
            logger.error("openrouter_error", error=str(e))
            return {"success": False, "error": str(e), "text": ""}

    async def analyze_screenshot(
        self, prompt: str, image_bytes: bytes, system: Optional[str] = None
    ) -> dict:
        # OpenRouter vision via LLaVA / Qwen-VL
        import base64
        image_b64 = base64.b64encode(image_bytes).decode()
        content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
        ]
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": content})

        payload = {
            "model": "qwen/qwen-vl-plus",
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 4096,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=25) as client:
                r = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
                r.raise_for_status()
                data = r.json()
                text = data["choices"][0]["message"]["content"]
                return {"success": True, "text": text, "raw": data}
        except Exception as e:
            return {"success": False, "error": str(e), "text": ""}
