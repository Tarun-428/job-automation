from typing import Optional
from dataclasses import dataclass

from config.settings import get_settings
from config.logging import get_logger
from ai.providers.ollama import OllamaProvider
from ai.providers.gemini import GeminiProvider
from ai.providers.openrouter import OpenRouterProvider
from ai.providers.groq import GroqProvider
from ai.providers.anthropic import AnthropicProvider
from ai.confidence import extract_confidence_from_text

logger = get_logger(__name__)


@dataclass
class AIResponse:
    text: str
    provider: str
    model: str
    confidence: float
    success: bool
    error: Optional[str] = None


class AIRouter:
    """
    Local-first AI router with cascading fallback to cloud providers.
    Routes text and vision (screenshot) requests.
    """

    def __init__(self):
        self.settings = get_settings()
        self._ollama = OllamaProvider()
        self._gemini = GeminiProvider()
        self._openrouter = OpenRouterProvider()
        self._groq = GroqProvider()
        self._anthropic = AnthropicProvider()

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        force_cloud: bool = False,
    ) -> AIResponse:
        """Route a text generation request through the provider chain."""
        if self.settings.ai_local_first and not force_cloud:
            result = await self._ollama.generate_text(prompt, system)
            if result["success"]:
                conf = extract_confidence_from_text(result["text"])
                if conf >= self.settings.ai_confidence_threshold:
                    return AIResponse(
                        text=result["text"],
                        provider="ollama",
                        model=self.settings.ollama_text_model,
                        confidence=conf,
                        success=True,
                    )
                logger.info("ollama_low_confidence", confidence=conf, falling_back=True)
            else:
                logger.info("ollama_failed", error=result.get("error"), falling_back=True)

        # Gemini Flash
        result = await self._gemini.generate_text(prompt, system)
        if result["success"]:
            conf = extract_confidence_from_text(result["text"])
            return AIResponse(
                text=result["text"], provider="gemini",
                model="gemini-1.5-flash", confidence=conf, success=True,
            )

        # Groq
        result = await self._groq.generate_text(prompt, system)
        if result["success"]:
            conf = extract_confidence_from_text(result["text"])
            return AIResponse(
                text=result["text"], provider="groq",
                model="llama-3.1-70b", confidence=conf, success=True,
            )

        # OpenRouter
        result = await self._openrouter.generate_text(prompt, system)
        if result["success"]:
            conf = extract_confidence_from_text(result["text"])
            return AIResponse(
                text=result["text"], provider="openrouter",
                model="llama-3.1-70b-instruct", confidence=conf, success=True,
            )

        # Claude premium fallback
        result = await self._anthropic.generate_text(prompt, system)
        if result["success"]:
            conf = extract_confidence_from_text(result["text"])
            return AIResponse(
                text=result["text"], provider="anthropic",
                model="claude-sonnet-4-5", confidence=conf, success=True,
            )

        return AIResponse(
            text="", provider="none", model="none",
            confidence=0.0, success=False, error="all_providers_failed",
        )

    async def analyze_screenshot(
        self,
        prompt: str,
        image_bytes: bytes,
        system: Optional[str] = None,
        force_cloud: bool = False,
    ) -> AIResponse:
        """Route a vision/screenshot analysis request through the provider chain."""
        if self.settings.ai_local_first and not force_cloud:
            result = await self._ollama.analyze_screenshot(prompt, image_bytes, system)
            if result["success"]:
                conf = extract_confidence_from_text(result["text"])
                if conf >= self.settings.ai_confidence_threshold:
                    return AIResponse(
                        text=result["text"], provider="ollama",
                        model=self.settings.ollama_multimodal_model,
                        confidence=conf, success=True,
                    )

        # Gemini Flash (vision capable)
        result = await self._gemini.analyze_screenshot(prompt, image_bytes, system)
        if result["success"]:
            conf = extract_confidence_from_text(result["text"])
            return AIResponse(
                text=result["text"], provider="gemini",
                model="gemini-1.5-flash", confidence=conf, success=True,
            )

        # OpenRouter vision
        result = await self._openrouter.analyze_screenshot(prompt, image_bytes, system)
        if result["success"]:
            conf = extract_confidence_from_text(result["text"])
            return AIResponse(
                text=result["text"], provider="openrouter",
                model="qwen-vl-plus", confidence=conf, success=True,
            )

        # Claude (vision)
        result = await self._anthropic.analyze_screenshot(prompt, image_bytes, system)
        if result["success"]:
            conf = extract_confidence_from_text(result["text"])
            return AIResponse(
                text=result["text"], provider="anthropic",
                model="claude-sonnet-4-5", confidence=conf, success=True,
            )

        return AIResponse(
            text="", provider="none", model="none",
            confidence=0.0, success=False, error="all_vision_providers_failed",
        )
