from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(request: Request):
    """System health check."""
    from ai.providers.ollama import OllamaProvider
    import redis.asyncio as aioredis

    ollama = OllamaProvider()
    ollama_ok = await ollama.health_check()

    settings = request.app.state.settings
    redis_ok = False
    try:
        r = await aioredis.from_url(settings.redis_url)
        await r.ping()
        redis_ok = True
    except Exception:
        pass

    return {
        "status": "ok",
        "ollama": ollama_ok,
        "redis": redis_ok,
    }
