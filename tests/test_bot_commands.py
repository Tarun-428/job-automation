"""Tests for /update and /revert bot commands."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from datetime import datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bot():
    """Create a TelegramBot with mocked notifier and workflow trigger."""
    from telegram.bot import TelegramBot
    notifier = MagicMock()
    notifier.send_message = AsyncMock(return_value=True)
    notifier.send_typing = AsyncMock()
    workflow_trigger = AsyncMock()
    bot = TelegramBot(notifier=notifier, workflow_trigger_fn=workflow_trigger)
    return bot


def _make_update(text: str, user_id: int = 42) -> dict:
    return {
        "message": {
            "chat": {"id": user_id},
            "from": {"id": user_id, "username": "testuser"},
            "text": text,
        }
    }


def _mock_user(onboarding_complete: bool = True):
    user = MagicMock()
    user.id = "00000000-0000-0000-0000-000000000001"
    user.onboarding_complete = onboarding_complete
    return user


def _mock_app(status: str = "running", job_title: str = "Engineer", company: str = "ACME"):
    app = MagicMock()
    app.id = "00000000-0000-0000-0000-000000000002"
    app.status = status
    app.job_title = job_title
    app.company = company
    app.job_url = "https://www.linkedin.com/jobs/view/123"
    app.workflow_id = "apply-abc123"
    app.error_message = None
    return app


# ---------------------------------------------------------------------------
# /update command
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_no_account():
    bot = _make_bot()
    with patch("telegram.bot.get_db_session") as mock_db:
        mock_session = AsyncMock()
        mock_db.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_users_repo = AsyncMock()
        mock_users_repo.get_by_telegram_id = AsyncMock(return_value=None)
        with patch("telegram.bot.UsersRepository", return_value=mock_users_repo):
            await bot.handle_update(_make_update("/update"))

    bot.notifier.send_message.assert_awaited_once()
    msg = bot.notifier.send_message.call_args[0][1]
    assert "No account found" in msg


@pytest.mark.asyncio
async def test_update_no_applications():
    bot = _make_bot()
    user = _mock_user()
    with patch("telegram.bot.get_db_session") as mock_db:
        mock_session = AsyncMock()
        mock_db.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_users_repo = AsyncMock()
        mock_users_repo.get_by_telegram_id = AsyncMock(return_value=user)
        mock_apps_repo = AsyncMock()
        mock_apps_repo.get_latest_by_user = AsyncMock(return_value=None)
        with patch("telegram.bot.UsersRepository", return_value=mock_users_repo), \
             patch("db.repositories.applications.ApplicationsRepository", return_value=mock_apps_repo):
            # Patch inside the method's local import
            import db.repositories.applications as apps_mod
            orig = apps_mod.ApplicationsRepository
            apps_mod.ApplicationsRepository = lambda _: mock_apps_repo
            await bot.handle_update(_make_update("/update"))
            apps_mod.ApplicationsRepository = orig

    bot.notifier.send_message.assert_awaited_once()
    msg = bot.notifier.send_message.call_args[0][1]
    assert "No applications" in msg


@pytest.mark.asyncio
async def test_update_shows_stepwise_log():
    bot = _make_bot()
    user = _mock_user()
    app = _mock_app(status="running")

    # Create a fake audit log entry
    log_entry = MagicMock()
    log_entry.created_at = datetime(2024, 1, 1, 12, 0, 0)
    log_entry.event_type = "navigate_and_analyze_complete"

    mock_apps_repo = AsyncMock()
    mock_apps_repo.get_latest_by_user = AsyncMock(return_value=app)
    mock_apps_repo.get_audit_logs = AsyncMock(return_value=[log_entry])

    with patch("telegram.bot.get_db_session") as mock_db:
        mock_session = AsyncMock()
        mock_db.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_users_repo = AsyncMock()
        mock_users_repo.get_by_telegram_id = AsyncMock(return_value=user)
        with patch("telegram.bot.UsersRepository", return_value=mock_users_repo):
            import db.repositories.applications as apps_mod
            orig = apps_mod.ApplicationsRepository
            apps_mod.ApplicationsRepository = lambda _: mock_apps_repo
            await bot.handle_update(_make_update("/update"))
            apps_mod.ApplicationsRepository = orig

    bot.notifier.send_message.assert_awaited_once()
    msg = bot.notifier.send_message.call_args[0][1]
    assert "Application Update" in msg
    assert "running" in msg
    assert "navigate_and_analyze_complete" in msg


# ---------------------------------------------------------------------------
# /revert command
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_revert_no_account():
    bot = _make_bot()
    with patch("telegram.bot.get_db_session") as mock_db:
        mock_session = AsyncMock()
        mock_db.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_users_repo = AsyncMock()
        mock_users_repo.get_by_telegram_id = AsyncMock(return_value=None)
        with patch("telegram.bot.UsersRepository", return_value=mock_users_repo):
            await bot.handle_update(_make_update("/revert"))

    msg = bot.notifier.send_message.call_args[0][1]
    assert "No account found" in msg


@pytest.mark.asyncio
async def test_revert_already_completed():
    bot = _make_bot()
    user = _mock_user()
    app = _mock_app(status="completed")

    mock_apps_repo = AsyncMock()
    mock_apps_repo.get_latest_by_user = AsyncMock(return_value=app)
    mock_apps_repo.revert = AsyncMock()

    with patch("telegram.bot.get_db_session") as mock_db:
        mock_session = AsyncMock()
        mock_db.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_users_repo = AsyncMock()
        mock_users_repo.get_by_telegram_id = AsyncMock(return_value=user)
        with patch("telegram.bot.UsersRepository", return_value=mock_users_repo):
            import db.repositories.applications as apps_mod
            orig = apps_mod.ApplicationsRepository
            apps_mod.ApplicationsRepository = lambda _: mock_apps_repo
            await bot.handle_update(_make_update("/revert"))
            apps_mod.ApplicationsRepository = orig

    # revert() should NOT have been called
    mock_apps_repo.revert.assert_not_awaited()
    msg = bot.notifier.send_message.call_args[0][1]
    assert "already" in msg.lower()


@pytest.mark.asyncio
async def test_revert_cancels_running_application():
    bot = _make_bot()
    user = _mock_user()
    app = _mock_app(status="running")

    mock_apps_repo = AsyncMock()
    mock_apps_repo.get_latest_by_user = AsyncMock(return_value=app)
    mock_apps_repo.revert = AsyncMock()

    with patch("telegram.bot.get_db_session") as mock_db:
        mock_session = AsyncMock()
        mock_db.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_users_repo = AsyncMock()
        mock_users_repo.get_by_telegram_id = AsyncMock(return_value=user)
        with patch("telegram.bot.UsersRepository", return_value=mock_users_repo):
            import db.repositories.applications as apps_mod
            orig = apps_mod.ApplicationsRepository
            apps_mod.ApplicationsRepository = lambda _: mock_apps_repo
            await bot.handle_update(_make_update("/revert"))
            apps_mod.ApplicationsRepository = orig

    mock_apps_repo.revert.assert_awaited_once()
    msg = bot.notifier.send_message.call_args[0][1]
    assert "reverted" in msg.lower()


@pytest.mark.asyncio
async def test_linkedin_prompt_without_url():
    bot = _make_bot()
    await bot.handle_update(_make_update("apply on linkdin"))
    bot.notifier.send_message.assert_awaited_once()
    msg = bot.notifier.send_message.call_args[0][1].lower()
    assert "linkedin" in msg
    assert "jobs/view" in msg
