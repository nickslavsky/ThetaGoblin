from unittest.mock import patch, call
from django.test import TestCase
from django.core.management import call_command
import io


class RunFundamentalsPipelineTest(TestCase):

    @patch("screener.management.commands.run_fundamentals_pipeline.call_command")
    def test_calls_both_subcommands(self, mock_call):
        call_command("run_fundamentals_pipeline")
        calls = [c[0][0] for c in mock_call.call_args_list]
        self.assertIn("pull_fundamentals", calls)
        self.assertIn("pull_earnings", calls)

    @patch("screener.management.commands.run_fundamentals_pipeline.call_command")
    def test_pull_fundamentals_called_before_earnings(self, mock_call):
        call_command("run_fundamentals_pipeline")
        calls = [c[0][0] for c in mock_call.call_args_list]
        self.assertLess(calls.index("pull_fundamentals"), calls.index("pull_earnings"))


class RunIvPipelineTest(TestCase):

    @patch("screener.management.commands.run_iv_pipeline.call_command")
    def test_calls_pull_iv_then_compute_iv_rank(self, mock_call):
        call_command("run_iv_pipeline")
        calls = [c[0][0] for c in mock_call.call_args_list]
        self.assertIn("pull_iv", calls)
        self.assertIn("compute_iv_rank", calls)
        self.assertLess(calls.index("pull_iv"), calls.index("compute_iv_rank"))

    @patch("screener.management.commands.run_iv_pipeline.call_command")
    def test_skips_iv_rank_when_pull_iv_fails(self, mock_call):
        """If pull_iv raises SystemExit, compute_iv_rank should not run."""
        mock_call.side_effect = lambda cmd, **kw: (_ for _ in ()).throw(
            SystemExit(1)
        ) if cmd == "pull_iv" else None
        call_command("run_iv_pipeline")
        calls = [c[0][0] for c in mock_call.call_args_list]
        self.assertIn("pull_iv", calls)
        self.assertNotIn("compute_iv_rank", calls)
