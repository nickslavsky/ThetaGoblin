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

    # IV refresh from DoltHub + rank computation: daily at 8 PM ET
    scheduler.add_job(
        lambda: call_command("run_iv_pipeline"),
        trigger=CronTrigger(hour=20, minute=0, timezone="America/New_York"),
        id="iv_pipeline",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        "APScheduler started: fundamentals Fri 18:00, "
        "IV daily 20:00 ET"
    )
