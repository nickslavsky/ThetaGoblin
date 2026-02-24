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


class RunOptionsPipelineTest(TestCase):

    @patch("screener.management.commands.run_options_pipeline.call_command")
    def test_calls_pull_options(self, mock_call):
        call_command("run_options_pipeline")
        calls = [c[0][0] for c in mock_call.call_args_list]
        self.assertIn("pull_options", calls)

    @patch("screener.management.commands.run_options_pipeline.call_command")
    def test_calls_compute_iv_rank_after_pull_options(self, mock_call):
        call_command("run_options_pipeline")
        calls = [c[0][0] for c in mock_call.call_args_list]
        self.assertIn("compute_iv_rank", calls)
        self.assertLess(calls.index("pull_options"), calls.index("compute_iv_rank"))
