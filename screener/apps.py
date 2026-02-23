from django.apps import AppConfig


class ScreenerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "screener"

    def ready(self):
        import os
        # Only start the scheduler in the web process, not in management commands or tests.
        # Set RUN_SCHEDULER=false in the environment to disable.
        if os.environ.get("RUN_SCHEDULER", "true").lower() in ("true", "1"):
            from screener import scheduler
            scheduler.start()
