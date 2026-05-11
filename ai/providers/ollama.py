import base64
from typing import Optional
import httpx
from config.settings import get_settings
from config.logging import get_logger

logger = get_logger(__name__)


class OllamaProvider:
    def __init__(self):
        settings = get_settings()
        self.host = settings.ollama_host
        self.multimodal_model = settings.ollama_multimodal_model
        self.text_model = settings.ollama_text_model
        self.timeout = settings.ollama_timeout

    async def generate_text(self, prompt: str, system: Optional[str] = None) -> dict:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.text_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.1},
        }
        return await self._post("/api/chat", payload)

    async def analyze_screenshot(
        self, prompt: str, image_bytes: bytes, system: Optional[str] = None
    ) -> dict:
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
            "model": self.multimodal_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.1},
        }
        return await self._post("/api/chat", payload)

    async def _post(self, endpoint: str, payload: dict) -> dict:
        url = f"{self.host}{endpoint}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                text = data.get("message", {}).get("content", "")
                return {"success": True, "text": text, "raw": data}
        except httpx.TimeoutException:
            logger.warning("ollama_timeout", endpoint=endpoint)
            return {"success": False, "error": "timeout", "text": ""}
        except Exception as e:
            logger.error("ollama_error", error=str(e))
            return {"success": False, "error": str(e), "text": ""}

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                r = await client.get(f"{self.host}/api/tags")
                return r.status_code == 200
        except Exception:
            return False
