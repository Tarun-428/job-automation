from fastapi import APIRouter, Request, HTTPException
from config.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post("/webhook")
async def telegram_webhook(request: Request):
    """Receive updates from Telegram webhook."""
    try:
        update = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    bot = request.app.state.telegram_bot
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not initialized")

    try:
        await bot.handle_update(update)
    except Exception as e:
        logger.error("webhook_handler_error", error=str(e))
        # Always return 200 to Telegram to avoid retries
    return {"ok": True}


@router.get("/set_webhook")
async def set_webhook(request: Request):
    """Set Telegram webhook URL."""
    from config.settings import get_settings
    import httpx

    settings = get_settings()
    webhook_url = f"{settings.telegram_webhook_url}"
    token = settings.telegram_bot_token

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"https://api.telegram.org/bot{token}/setWebhook",
            json={"url": webhook_url, "allowed_updates": ["message", "edited_message"]},
        )
        return r.json()
