from datetime import date, timedelta
from unittest.mock import patch
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

    @patch("screener.services.finnhub_client.fetch_earnings")
    def test_creates_earnings_dates(self, mock_fetch):
        today = date.today()
        mock_fetch.return_value = [
            {"symbol": "AAPL", "date": (today + timedelta(days=30)).isoformat()},
            {"symbol": "MSFT", "date": (today + timedelta(days=45)).isoformat()},
        ]
        call_command("pull_earnings")
        self.assertEqual(EarningsDate.objects.count(), 2)

    @patch("screener.services.finnhub_client.fetch_earnings")
    def test_skips_unknown_tickers(self, mock_fetch):
        today = date.today()
        mock_fetch.return_value = [
            {"symbol": "AAPL", "date": (today + timedelta(days=30)).isoformat()},
            {"symbol": "UNKNOWN_TICKER", "date": (today + timedelta(days=30)).isoformat()},
        ]
        call_command("pull_earnings")
        # Only AAPL should be stored — UNKNOWN_TICKER not in Symbol table
        self.assertEqual(EarningsDate.objects.count(), 1)
        self.assertTrue(EarningsDate.objects.filter(symbol=self.aapl).exists())

    @patch("screener.services.finnhub_client.fetch_earnings")
    def test_idempotent(self, mock_fetch):
        today = date.today()
        mock_fetch.return_value = [
            {"symbol": "AAPL", "date": (today + timedelta(days=30)).isoformat()},
        ]
        call_command("pull_earnings")
        call_command("pull_earnings")
        # Running twice should not create duplicate rows
        self.assertEqual(EarningsDate.objects.count(), 1)

    @patch("screener.services.finnhub_client.fetch_earnings")
    def test_handles_missing_fields(self, mock_fetch):
        mock_fetch.return_value = [
            {"symbol": None, "date": "2026-03-01"},  # missing symbol
            {"symbol": "AAPL", "date": None},  # missing date
            {},  # completely empty
        ]
        # Should not raise, should skip all rows
        call_command("pull_earnings")
        self.assertEqual(EarningsDate.objects.count(), 0)

    @patch("screener.services.finnhub_client.fetch_earnings")
    def test_weeks_ahead_argument(self, mock_fetch):
        mock_fetch.return_value = []
        call_command("pull_earnings", weeks_ahead=4)
        # Verify it was called with a date range ~4 weeks out
        args, kwargs = mock_fetch.call_args
        from_date = args[0]
        to_date = args[1]
        delta = date.fromisoformat(to_date) - date.fromisoformat(from_date)
        self.assertGreaterEqual(delta.days, 27)
        self.assertLessEqual(delta.days, 30)
