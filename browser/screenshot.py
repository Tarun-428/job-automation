import os
import uuid
from datetime import datetime
from typing import Optional
from pathlib import Path

from playwright.async_api import Page

from config.settings import get_settings
from config.logging import get_logger

logger = get_logger(__name__)


async def capture_screenshot(page: Page, step_name: str, user_id: str) -> tuple[bytes, str]:
    """
    Capture a screenshot of the current page.
    Returns (image_bytes, file_path).
    """
    settings = get_settings()
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{step_name}_{timestamp}_{uuid.uuid4().hex[:8]}.png"

    image_bytes = await page.screenshot(full_page=False, type="png")
    file_path = ""
    if settings.save_screenshots:
        user_dir = Path(settings.storage_local_path) / "screenshots" / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        file_path = str(user_dir / filename)
        with open(file_path, "wb") as f:
            f.write(image_bytes)
        logger.info("screenshot_captured", step=step_name, path=file_path)
    else:
        # Screenshot persistence can be disabled via SAVE_SCREENSHOTS=false
        logger.info("screenshot_skipped", step=step_name)

    return image_bytes, file_path


async def capture_full_page_screenshot(page: Page, step_name: str, user_id: str) -> tuple[bytes, str]:
    settings = get_settings()
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{step_name}_full_{timestamp}.png"

    image_bytes = await page.screenshot(full_page=True, type="png")
    file_path = ""
    if settings.save_screenshots:
        user_dir = Path(settings.storage_local_path) / "screenshots" / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        file_path = str(user_dir / filename)
        with open(file_path, "wb") as f:
            f.write(image_bytes)
    return image_bytes, file_path
