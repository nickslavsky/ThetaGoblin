from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.core.management import call_command
from django.utils.timezone import now
from screener.models import Symbol


@override_settings(YFINANCE_REQUEST_DELAY=0)
class PullFundamentalsTest(TestCase):

    def setUp(self):
        self.sym = Symbol.objects.create(
            ticker="AAPL", exchange_mic="XNAS", name="Apple Inc"
        )

    @patch("screener.services.yfinance_svc.fetch_fundamentals")
    def test_updates_stale_symbol(self, mock_fetch):
        mock_fetch.return_value = {
            "market_cap": 3_000_000_000_000,
            "operating_margin": 0.30,
            "free_cash_flow": 106_000_000_000,
            "debt_to_equity": 102.63,
            "avg_volume_10d": 43_000_000,
        }
        call_command("pull_fundamentals")
        self.sym.refresh_from_db()
        self.assertEqual(self.sym.market_cap, 3_000_000_000_000)
        self.assertIsNotNone(self.sym.fundamentals_updated_at)

    @patch("screener.services.yfinance_svc.fetch_fundamentals")
    def test_skips_recently_updated(self, mock_fetch):
        mock_fetch.return_value = {
            "market_cap": 1_000_000_000, "operating_margin": 0.1,
            "free_cash_flow": 50_000_000, "debt_to_equity": 50.0,
            "avg_volume_10d": 1_000_000,
        }
        self.sym.fundamentals_updated_at = now()
        self.sym.save()
        call_command("pull_fundamentals", stale_days=7)
        mock_fetch.assert_not_called()

    @patch("screener.services.yfinance_svc.fetch_fundamentals")
    def test_handles_api_failure_gracefully(self, mock_fetch):
        mock_fetch.return_value = None
        call_command("pull_fundamentals")
        self.sym.refresh_from_db()
        self.assertIsNone(self.sym.fundamentals_updated_at)

    @patch("screener.services.yfinance_svc.fetch_fundamentals")
    def test_limit_option(self, mock_fetch):
        mock_fetch.return_value = {
            "market_cap": 1_000_000_000, "operating_margin": 0.1,
            "free_cash_flow": 50_000_000, "debt_to_equity": 50.0,
            "avg_volume_10d": 1_000_000,
        }
        Symbol.objects.create(ticker="MSFT", exchange_mic="XNAS", name="Microsoft")
        Symbol.objects.create(ticker="GOOG", exchange_mic="XNAS", name="Alphabet")
        call_command("pull_fundamentals", limit=1)
        self.assertEqual(mock_fetch.call_count, 1)
