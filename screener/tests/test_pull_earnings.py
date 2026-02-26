from datetime import date, timedelta
from unittest.mock import call, patch
from django.test import TestCase
from django.core.management import call_command
from screener.models import Symbol, EarningsDate


class PullEarningsTest(TestCase):

    def setUp(self):
        self.aapl = Symbol.objects.create(
            ticker="AAPL", exchange_mic="XNAS", name="Apple Inc"
        )
        self.msft = Symbol.objects.create(
            ticker="MSFT", exchange_mic="XNAS", name="Microsoft Corp"
        )

    @patch("screener.management.commands.pull_earnings.time.sleep")
    @patch("screener.services.finnhub_client.fetch_earnings")
    def test_creates_earnings_dates(self, mock_fetch, mock_sleep):
        today = date.today()
        # Return data only on the first chunk call; subsequent chunks return empty
        mock_fetch.side_effect = lambda from_d, to_d: [
            {"symbol": "AAPL", "date": (today + timedelta(days=30)).isoformat()},
            {"symbol": "MSFT", "date": (today + timedelta(days=45)).isoformat()},
        ] if from_d == today.isoformat() else []
        call_command("pull_earnings")
        self.assertEqual(EarningsDate.objects.count(), 2)

    @patch("screener.management.commands.pull_earnings.time.sleep")
    @patch("screener.services.finnhub_client.fetch_earnings")
    def test_skips_unknown_tickers(self, mock_fetch, mock_sleep):
        today = date.today()
        mock_fetch.side_effect = lambda from_d, to_d: [
            {"symbol": "AAPL", "date": (today + timedelta(days=30)).isoformat()},
            {"symbol": "UNKNOWN_TICKER", "date": (today + timedelta(days=30)).isoformat()},
        ] if from_d == today.isoformat() else []
        call_command("pull_earnings")
        # Only AAPL should be stored — UNKNOWN_TICKER not in Symbol table
        self.assertEqual(EarningsDate.objects.count(), 1)
        self.assertTrue(EarningsDate.objects.filter(symbol=self.aapl).exists())

    @patch("screener.management.commands.pull_earnings.time.sleep")
    @patch("screener.services.finnhub_client.fetch_earnings")
    def test_idempotent(self, mock_fetch, mock_sleep):
        today = date.today()
        mock_fetch.side_effect = lambda from_d, to_d: [
            {"symbol": "AAPL", "date": (today + timedelta(days=30)).isoformat()},
        ] if from_d == today.isoformat() else []
        call_command("pull_earnings")
        call_command("pull_earnings")
        # Running twice should not create duplicate rows
        self.assertEqual(EarningsDate.objects.count(), 1)

    @patch("screener.management.commands.pull_earnings.time.sleep")
    @patch("screener.services.finnhub_client.fetch_earnings")
    def test_handles_missing_fields(self, mock_fetch, mock_sleep):
        mock_fetch.side_effect = lambda from_d, to_d: [
            {"symbol": None, "date": "2026-03-01"},  # missing symbol
            {"symbol": "AAPL", "date": None},  # missing date
            {},  # completely empty
        ] if mock_fetch.call_count == 1 else []
        # Should not raise, should skip all rows
        call_command("pull_earnings")
        self.assertEqual(EarningsDate.objects.count(), 0)

    @patch("screener.management.commands.pull_earnings.time.sleep")
    @patch("screener.services.finnhub_client.fetch_earnings")
    def test_chunked_into_weekly_calls(self, mock_fetch, mock_sleep):
        """Verifies the command makes one API call per week, not one for the full range."""
        mock_fetch.return_value = []
        call_command("pull_earnings", weeks_ahead=4)
        # today + 4 weeks = 4*7+1 = 29 days inclusive → ceil(29/7) = 5 chunks
        # (4 full 7-day chunks + 1 partial final day)
        self.assertEqual(mock_fetch.call_count, 5)
        # First call starts at today
        first_from, first_to = mock_fetch.call_args_list[0][0]
        self.assertEqual(first_from, date.today().isoformat())
        # First full chunk is 6 days wide (days 0–6 inclusive = 7 days)
        first_delta = date.fromisoformat(first_to) - date.fromisoformat(first_from)
        self.assertEqual(first_delta.days, 6)
        # Last call ends exactly at today + 4 weeks
        last_from, last_to = mock_fetch.call_args_list[-1][0]
        expected_end = date.today() + timedelta(weeks=4)
        self.assertEqual(date.fromisoformat(last_to), expected_end)

    @patch("screener.management.commands.pull_earnings.time.sleep")
    @patch("screener.services.finnhub_client.fetch_earnings")
    def test_sleep_between_chunks(self, mock_fetch, mock_sleep):
        """Verifies a sleep is inserted between chunks but not after the last one."""
        mock_fetch.return_value = []
        call_command("pull_earnings", weeks_ahead=3)
        # today + 3 weeks = 22 days inclusive → 4 chunks, 3 sleeps (not after last)
        self.assertEqual(mock_sleep.call_count, 3)
