from datetime import timedelta
from typing import Optional

from temporalio import workflow
from temporalio.common import RetryPolicy

MAX_ERROR_NOTIFICATION_LENGTH = 200

with workflow.unsafe.imports_passed_through():
    from workflows.activities.browser_activities import (
        navigate_and_analyze_activity,
        generate_resume_activity,
        fill_and_submit_activity,
        send_notification_activity,
        update_application_status_activity,
    )


@workflow.defn
class JobApplicationWorkflow:
    """
    Main Temporal workflow for autonomous job application.
    Handles retries, long-running steps, and crash recovery.

    Stepwise Telegram notifications are sent after every major phase so the
    user always knows what is happening.  Fatal errors trigger an auto-revert
    that marks the application as 'reverted' in the database and notifies the
    user via Telegram.
    """

    @workflow.run
    async def run(
        self,
        user_id: str,
        telegram_user_id: int,
        job_url: str,
        application_id: str,
    ) -> dict:
        retry_policy = RetryPolicy(
            maximum_attempts=3,
            initial_interval=timedelta(seconds=5),
            maximum_interval=timedelta(minutes=2),
            backoff_coefficient=2.0,
        )

        result = {
            "submitted": False,
            "confirmation_id": None,
            "error": None,
        }

        # ── Step 1: Navigate and analyze the job posting ─────────────────────
        await workflow.execute_activity(
            send_notification_activity,
            args=[telegram_user_id, "🔍 *Step 1/3* — Navigating to the job posting…"],
            start_to_close_timeout=timedelta(seconds=30),
        )

        try:
            job_info = await workflow.execute_activity(
                navigate_and_analyze_activity,
                args=[user_id, job_url, telegram_user_id, application_id],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=retry_policy,
            )
        except Exception as e:
            error_msg = str(e)[:MAX_ERROR_NOTIFICATION_LENGTH]
            # Auto-revert: mark the application as reverted and notify the user
            await workflow.execute_activity(
                update_application_status_activity,
                args=[application_id, "reverted", f"Navigation failed: {error_msg}"],
                start_to_close_timeout=timedelta(seconds=30),
            )
            await workflow.execute_activity(
                send_notification_activity,
                args=[
                    telegram_user_id,
                    f"❌ *Step 1 failed* — Could not load the job posting.\n\n"
                    f"Reason: `{error_msg}`\n\n"
                    "The application has been automatically reverted. "
                    "Please verify the URL and try again.",
                ],
                start_to_close_timeout=timedelta(seconds=30),
            )
            result["error"] = error_msg
            return result

        platform = job_info.get("platform", "custom")
        raw_jd = job_info.get("raw_jd", "")
        job_title = job_info.get("job_title", "Unknown")
        company = job_info.get("company", "Unknown")

        await workflow.execute_activity(
            update_application_status_activity,
            args=[
                application_id,
                "running",
                None,
                job_title,
                company,
                platform,
                None,
            ],
            start_to_close_timeout=timedelta(seconds=30),
        )

        await workflow.execute_activity(
            send_notification_activity,
            args=[
                telegram_user_id,
                f"✅ *Step 1/3 complete* — Job posting analyzed.\n"
                f"💼 *{job_title}* @ *{company}* ({platform})",
            ],
            start_to_close_timeout=timedelta(seconds=30),
        )

        # ── Step 2: Generate a tailored resume ───────────────────────────────
        await workflow.execute_activity(
            send_notification_activity,
            args=[telegram_user_id, "📄 *Step 2/3* — Generating your tailored resume…"],
            start_to_close_timeout=timedelta(seconds=30),
        )

        try:
            pdf_path = await workflow.execute_activity(
                generate_resume_activity,
                args=[user_id, raw_jd, application_id],
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=retry_policy,
            )
            await workflow.execute_activity(
                send_notification_activity,
                args=[telegram_user_id, "✅ *Step 2/3 complete* — Resume generated successfully."],
                start_to_close_timeout=timedelta(seconds=30),
            )
        except Exception as e:
            workflow.logger.warning(f"Resume generation failed: {e}, continuing without resume")
            pdf_path = None
            await workflow.execute_activity(
                send_notification_activity,
                args=[
                    telegram_user_id,
                    f"⚠️ *Step 2/3* — Resume generation failed (`{str(e)[:100]}`). "
                    "Continuing without a tailored resume.",
                ],
                start_to_close_timeout=timedelta(seconds=30),
            )

        # ── Step 3: Fill form and submit ─────────────────────────────────────
        await workflow.execute_activity(
            send_notification_activity,
            args=[telegram_user_id, "📝 *Step 3/3* — Filling the application form…"],
            start_to_close_timeout=timedelta(seconds=30),
        )

        try:
            submit_result = await workflow.execute_activity(
                fill_and_submit_activity,
                args=[user_id, telegram_user_id, job_url, platform, application_id, pdf_path],
                start_to_close_timeout=timedelta(minutes=20),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
            result.update(submit_result)

            if result.get("submitted"):
                await workflow.execute_activity(
                    update_application_status_activity,
                    args=[
                        application_id,
                        "completed",
                        None,
                        job_title,
                        company,
                        platform,
                        result.get("confirmation_id"),
                    ],
                    start_to_close_timeout=timedelta(seconds=30),
                )
                await workflow.execute_activity(
                    send_notification_activity,
                    args=[
                        telegram_user_id,
                        f"🎉 *Application submitted!*\n\n"
                        f"💼 {job_title} @ {company}\n"
                        f"🔗 {job_url[:80]}\n\n"
                        "Check /status for full details.",
                    ],
                    start_to_close_timeout=timedelta(seconds=30),
                )
            else:
                error_detail = result.get("error") or "Unknown reason"
                await workflow.execute_activity(
                    update_application_status_activity,
                    args=[
                        application_id,
                        "failed",
                        error_detail[:MAX_ERROR_NOTIFICATION_LENGTH],
                        job_title,
                        company,
                        platform,
                        None,
                    ],
                    start_to_close_timeout=timedelta(seconds=30),
                )
                await workflow.execute_activity(
                    send_notification_activity,
                    args=[
                        telegram_user_id,
                        f"⚠️ *Step 3/3* — Form submission was not completed.\n"
                        f"Reason: `{error_detail[:MAX_ERROR_NOTIFICATION_LENGTH]}`",
                    ],
                    start_to_close_timeout=timedelta(seconds=30),
                )

        except Exception as e:
            error_msg = str(e)[:MAX_ERROR_NOTIFICATION_LENGTH]
            result["error"] = error_msg
            # Auto-revert on fatal submission failure
            await workflow.execute_activity(
                update_application_status_activity,
                args=[application_id, "reverted", f"Submission failed: {error_msg}"],
                start_to_close_timeout=timedelta(seconds=30),
            )
            await workflow.execute_activity(
                send_notification_activity,
                args=[
                    telegram_user_id,
                    f"❌ *Step 3 failed* — Application workflow encountered a fatal error.\n\n"
                    f"Reason: `{error_msg}`\n\n"
                    "The application has been automatically reverted. "
                    "Use /status to review or send a new URL to try again.",
                ],
                start_to_close_timeout=timedelta(seconds=30),
            )

        return result
