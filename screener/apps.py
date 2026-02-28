from django.apps import AppConfig


class ScreenerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "screener"

    def ready(self):
        import os
        # Only start the scheduler in the web process, not in management commands or tests.
        # Set RUN_SCHEDULER=false in the environment to disable.
        # Django's runserver with autoreload spawns two processes — the reloader
        # (parent) and the actual server (child, RUN_MAIN=true). Only start in
        # the child to avoid duplicate cron jobs.
        if os.environ.get("RUN_SCHEDULER", "true").lower() in ("true", "1"):
            if os.environ.get("RUN_MAIN") == "true":
                from screener import scheduler
                scheduler.start()
