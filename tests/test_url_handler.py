"""Tests for LinkedIn URL validation logic in URLHandler."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram.handlers.url_handler import URLHandler, LINKEDIN_JOB_RE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_handler() -> URLHandler:
    """Return a URLHandler with a mocked TelegramNotifier."""
    notifier = MagicMock()
    notifier.send_message = AsyncMock(return_value=True)
    notifier.send_typing = AsyncMock()
    return URLHandler(notifier)


# ---------------------------------------------------------------------------
# extract_url
# ---------------------------------------------------------------------------

def test_extract_url_finds_url():
    h = make_handler()
    assert h.extract_url("Check this https://example.com/job/123") == "https://example.com/job/123"


def test_extract_url_returns_none_when_missing():
    h = make_handler()
    assert h.extract_url("no url here") is None


# ---------------------------------------------------------------------------
# is_linkedin_url
# ---------------------------------------------------------------------------

def test_is_linkedin_url_true():
    h = make_handler()
    assert h.is_linkedin_url("https://www.linkedin.com/jobs/view/123456") is True


def test_is_linkedin_url_false_for_other_domains():
    h = make_handler()
    assert h.is_linkedin_url("https://boards.greenhouse.io/company/jobs/1") is False


def test_is_linkedin_url_rejects_phishing_host():
    """A URL whose path contains 'linkedin.com' but whose host is not LinkedIn."""
    h = make_handler()
    assert h.is_linkedin_url("https://phishing.com/redirect?to=linkedin.com") is False


def test_is_linkedin_url_accepts_subdomain():
    h = make_handler()
    assert h.is_linkedin_url("https://www.linkedin.com/jobs/view/123") is True


# ---------------------------------------------------------------------------
# is_valid_linkedin_job_url
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "https://www.linkedin.com/jobs/view/1234567890",
    "https://linkedin.com/jobs/view/42",
    "http://www.linkedin.com/jobs/view/9999",
])
def test_valid_linkedin_job_urls(url):
    h = make_handler()
    assert h.is_valid_linkedin_job_url(url) is True


@pytest.mark.parametrize("url", [
    # Missing numeric ID
    "https://www.linkedin.com/jobs/view/",
    # Wrong path (search, not view)
    "https://www.linkedin.com/jobs/search/?keywords=python",
    # Profile URL, not job
    "https://www.linkedin.com/in/someone",
    # Completely different domain
    "https://boards.greenhouse.io/company/jobs/1",
    # Empty string
    "",
])
def test_invalid_linkedin_job_urls(url):
    h = make_handler()
    assert h.is_valid_linkedin_job_url(url) is False


# ---------------------------------------------------------------------------
# handle — LinkedIn-specific validation branch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_rejects_bad_linkedin_format():
    """A LinkedIn URL that doesn't match /jobs/view/<id> should be rejected."""
    h = make_handler()
    await h.handle(
        telegram_user_id=1,
        telegram_username="testuser",
        text="https://www.linkedin.com/in/someone",
        workflow_trigger_fn=AsyncMock(),
    )
    h.notifier.send_message.assert_awaited_once()
    msg = h.notifier.send_message.call_args[0][1]
    assert "Invalid LinkedIn URL" in msg or "invalid" in msg.lower()


@pytest.mark.asyncio
async def test_handle_rejects_unreachable_linkedin_url():
    """A well-formed LinkedIn job URL that returns a 404 should be rejected."""
    h = make_handler()
    with patch.object(h, "check_url_reachable", new=AsyncMock(return_value=False)):
        await h.handle(
            telegram_user_id=1,
            telegram_username="testuser",
            text="https://www.linkedin.com/jobs/view/9999999999",
            workflow_trigger_fn=AsyncMock(),
        )
    h.notifier.send_message.assert_awaited()
    msgs = [call[0][1] for call in h.notifier.send_message.call_args_list]
    assert any("not found" in m.lower() or "expired" in m.lower() for m in msgs)


@pytest.mark.asyncio
async def test_handle_proceeds_for_reachable_linkedin_url():
    """A valid, reachable LinkedIn job URL should trigger the workflow."""
    h = make_handler()
    workflow_fn = AsyncMock()

    # Patch DB calls so we don't need a real database
    mock_user = MagicMock()
    mock_user.onboarding_complete = True
    mock_user.id = "00000000-0000-0000-0000-000000000001"

    mock_app = MagicMock()
    mock_app.id = "00000000-0000-0000-0000-000000000002"

    with patch.object(h, "check_url_reachable", new=AsyncMock(return_value=True)), \
         patch("telegram.handlers.url_handler.get_db_session") as mock_db:
        # Build a minimal async-context-manager mock for the session
        mock_session = AsyncMock()
        mock_db.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_users_repo = AsyncMock()
        mock_users_repo.get_or_create = AsyncMock(return_value=(mock_user, False))
        mock_apps_repo = AsyncMock()
        mock_apps_repo.create = AsyncMock(return_value=mock_app)

        with patch("telegram.handlers.url_handler.UsersRepository", return_value=mock_users_repo), \
             patch("telegram.handlers.url_handler.ApplicationsRepository", return_value=mock_apps_repo):
            await h.handle(
                telegram_user_id=1,
                telegram_username="testuser",
                text="https://www.linkedin.com/jobs/view/1234567890",
                workflow_trigger_fn=workflow_fn,
            )

    workflow_fn.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_no_url_in_text():
    """Messages without a URL should get an error notification."""
    h = make_handler()
    await h.handle(
        telegram_user_id=1,
        telegram_username="testuser",
        text="just some random text",
        workflow_trigger_fn=AsyncMock(),
    )
    h.notifier.send_message.assert_awaited_once()
    msg = h.notifier.send_message.call_args[0][1]
    assert "No valid URL" in msg
