import os
import uuid
from datetime import datetime, timezone
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
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{step_name}_{timestamp}_{uuid.uuid4().hex[:8]}.png"

    image_bytes = await page.screenshot(full_page=False, type="png")
    file_path = ""
    if settings.save_screenshots:
        storage_root = Path(settings.storage_local_path)
        user_dir = storage_root / "screenshots" / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        file_path = str((user_dir / filename).resolve())
        with open(file_path, "wb") as f:
            f.write(image_bytes)
        logger.info(
            "screenshot_captured",
            step=step_name,
            path=file_path,
            storage_root=str(storage_root.resolve()),
        )
    else:
        # Screenshot persistence can be disabled via SAVE_SCREENSHOTS=false
        logger.info(
            "screenshot_skipped",
            step=step_name,
            reason="SAVE_SCREENSHOTS=false",
        )

    return image_bytes, file_path


async def capture_full_page_screenshot(page: Page, step_name: str, user_id: str) -> tuple[bytes, str]:
    settings = get_settings()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{step_name}_full_{timestamp}_{uuid.uuid4().hex[:8]}.png"

    image_bytes = await page.screenshot(full_page=True, type="png")
    file_path = ""
    if settings.save_screenshots:
        storage_root = Path(settings.storage_local_path)
        user_dir = storage_root / "screenshots" / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        file_path = str((user_dir / filename).resolve())
        with open(file_path, "wb") as f:
            f.write(image_bytes)
        logger.info(
            "screenshot_captured",
            step=step_name,
            path=file_path,
            storage_root=str(storage_root.resolve()),
        )
    else:
        logger.info(
            "screenshot_skipped",
            step=step_name,
            reason="SAVE_SCREENSHOTS=false",
        )
    return image_bytes, file_path
