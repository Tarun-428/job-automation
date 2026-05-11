from datetime import timedelta
from typing import Optional

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from workflows.activities.browser_activities import (
        navigate_and_analyze_activity,
        generate_resume_activity,
        fill_and_submit_activity,
        send_notification_activity,
    )


@workflow.defn
class JobApplicationWorkflow:
    """
    Main Temporal workflow for autonomous job application.
    Handles retries, long-running steps, and crash recovery.
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

        # Step 1: Navigate and analyze
        try:
            job_info = await workflow.execute_activity(
                navigate_and_analyze_activity,
                args=[user_id, job_url, telegram_user_id],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=retry_policy,
            )
        except Exception as e:
            await workflow.execute_activity(
                send_notification_activity,
                args=[telegram_user_id, f"❌ Failed to navigate to job URL: {str(e)[:200]}"],
                start_to_close_timeout=timedelta(seconds=30),
            )
            result["error"] = str(e)
            return result

        platform = job_info.get("platform", "custom")
        raw_jd = job_info.get("raw_jd", "")

        # Step 2: Generate resume
        try:
            pdf_path = await workflow.execute_activity(
                generate_resume_activity,
                args=[user_id, raw_jd, application_id],
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=retry_policy,
            )
        except Exception as e:
            workflow.logger.warning(f"Resume generation failed: {e}, continuing without resume")
            pdf_path = None

        # Step 3: Fill form and submit
        try:
            submit_result = await workflow.execute_activity(
                fill_and_submit_activity,
                args=[user_id, telegram_user_id, job_url, platform, application_id, pdf_path],
                start_to_close_timeout=timedelta(minutes=20),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
            result.update(submit_result)
        except Exception as e:
            result["error"] = str(e)
            await workflow.execute_activity(
                send_notification_activity,
                args=[telegram_user_id, f"❌ Application workflow failed: {str(e)[:200]}"],
                start_to_close_timeout=timedelta(seconds=30),
            )

        return result
