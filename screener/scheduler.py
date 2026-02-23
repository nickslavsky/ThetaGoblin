import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django.core.management import call_command

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def start():
    """Start the background scheduler with weekly pipeline jobs.

    Safe to call multiple times — will not start a second instance
    if already running.
    """
    if scheduler.running:
        logger.debug("Scheduler already running, skipping start")
        return

    # Fundamentals + earnings: every Friday at 6 PM ET (after US market close)
    scheduler.add_job(
        lambda: call_command("run_fundamentals_pipeline"),
        trigger=CronTrigger(day_of_week="fri", hour=18, minute=0, timezone="America/New_York"),
        id="fundamentals_pipeline",
        replace_existing=True,
    )

    # Options: every Friday at 7 PM ET (after fundamentals completes)
    scheduler.add_job(
        lambda: call_command("run_options_pipeline"),
        trigger=CronTrigger(day_of_week="fri", hour=19, minute=0, timezone="America/New_York"),
        id="options_pipeline",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("APScheduler started: fundamentals at Fri 18:00, options at Fri 19:00 ET")
