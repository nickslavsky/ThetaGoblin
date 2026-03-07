from unittest.mock import patch, MagicMock
from django.test import TestCase


class SchedulerTest(TestCase):

    def test_scheduler_module_importable(self):
        from screener import scheduler
        self.assertTrue(hasattr(scheduler, "start"))
        self.assertTrue(hasattr(scheduler, "scheduler"))

    @patch("screener.scheduler.BackgroundScheduler")
    def test_start_adds_three_jobs(self, mock_scheduler_cls):
        mock_sched = MagicMock()
        mock_sched.running = False
        mock_scheduler_cls.return_value = mock_sched

        # Re-import to pick up mock
        import importlib
        from screener import scheduler as sched_module
        # Reset module-level scheduler object
        sched_module.scheduler = mock_sched

        sched_module.start()
        self.assertEqual(mock_sched.add_job.call_count, 2)
        mock_sched.start.assert_called_once()

    @patch("screener.scheduler.BackgroundScheduler")
    def test_start_is_idempotent(self, mock_scheduler_cls):
        mock_sched = MagicMock()
        mock_sched.running = True  # already running
        mock_scheduler_cls.return_value = mock_sched

        import importlib
        from screener import scheduler as sched_module
        sched_module.scheduler = mock_sched

        sched_module.start()
        mock_sched.start.assert_not_called()
        mock_sched.add_job.assert_not_called()
