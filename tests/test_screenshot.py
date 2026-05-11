"""Tests for screenshot persistence toggle."""
import pytest
from types import SimpleNamespace

from browser.screenshot import capture_screenshot, capture_full_page_screenshot


class DummyPage:
    async def screenshot(self, full_page: bool, **kwargs):
        return b"image-bytes"


@pytest.mark.asyncio
async def test_capture_screenshot_does_not_save_when_disabled(monkeypatch, tmp_path):
    settings = SimpleNamespace(storage_local_path=str(tmp_path), save_screenshots=False)
    monkeypatch.setattr("browser.screenshot.get_settings", lambda: settings)

    image_bytes, file_path = await capture_screenshot(DummyPage(), "step", "user")

    assert image_bytes == b"image-bytes"
    assert file_path == ""
    assert list(tmp_path.rglob("*")) == []


@pytest.mark.asyncio
async def test_capture_full_page_screenshot_saves_when_enabled(monkeypatch, tmp_path):
    settings = SimpleNamespace(storage_local_path=str(tmp_path), save_screenshots=True)
    monkeypatch.setattr("browser.screenshot.get_settings", lambda: settings)

    image_bytes, file_path = await capture_full_page_screenshot(DummyPage(), "step", "user")

    assert image_bytes == b"image-bytes"
    assert file_path
    assert list(tmp_path.rglob("*.png"))
