import pytest
from unittest.mock import AsyncMock, patch
from ai.router import AIRouter, AIResponse


@pytest.fixture
def ai_router():
    return AIRouter()


@pytest.mark.asyncio
async def test_generate_falls_back_to_gemini_when_ollama_fails(ai_router):
    with patch.object(ai_router._ollama, "generate_text", return_value={"success": False, "error": "timeout", "text": ""}):
        with patch.object(ai_router._gemini, "generate_text", return_value={"success": True, "text": '{"answer": "test", "confidence": 0.9}'}):
            result = await ai_router.generate("test prompt")
            assert result.success
            assert result.provider == "gemini"


@pytest.mark.asyncio
async def test_generate_uses_ollama_when_available(ai_router):
    with patch.object(ai_router._ollama, "generate_text", return_value={"success": True, "text": '{"answer": "test", "confidence": 0.9}'}):
        result = await ai_router.generate("test prompt")
        assert result.success
        assert result.provider == "ollama"


@pytest.mark.asyncio
async def test_all_providers_fail_returns_failure(ai_router):
    failure = {"success": False, "error": "fail", "text": ""}
    with patch.object(ai_router._ollama, "generate_text", return_value=failure), \
         patch.object(ai_router._gemini, "generate_text", return_value=failure), \
         patch.object(ai_router._groq, "generate_text", return_value=failure), \
         patch.object(ai_router._openrouter, "generate_text", return_value=failure), \
         patch.object(ai_router._anthropic, "generate_text", return_value=failure):
        result = await ai_router.generate("test")
        assert not result.success
        assert result.provider == "none"
