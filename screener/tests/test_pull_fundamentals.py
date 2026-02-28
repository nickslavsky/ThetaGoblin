from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.core.management import call_command
from django.utils.timezone import now
from screener.models import Symbol


@override_settings(FINNHUB_REQUEST_DELAY=0)
class PullFundamentalsTest(TestCase):

    def setUp(self):
        self.sym = Symbol.objects.create(
            ticker="AAPL", exchange_mic="XNAS", name="Apple Inc"
        )

    @patch("screener.services.finnhub_client.fetch_fundamentals")
    def test_updates_stale_symbol(self, mock_fetch):
        mock_fetch.return_value = {
            "market_cap": 3_000_000_000_000,
            "operating_margin": 0.30,
            "cash_flow_per_share_annual": 7.5,
            "long_term_debt_to_equity_annual": 1.2,
            "ten_day_avg_trading_volume": 5_000_000.0,
        }
        call_command("pull_fundamentals")
        self.sym.refresh_from_db()
        self.assertEqual(self.sym.market_cap, 3_000_000_000_000)
        self.assertIsNotNone(self.sym.fundamentals_updated_at)

    @patch("screener.services.finnhub_client.fetch_fundamentals")
    def test_skips_recently_updated(self, mock_fetch):
        mock_fetch.return_value = {"market_cap": 1_000_000_000, "operating_margin": 0.1,
                                   "cash_flow_per_share_annual": 1.0,
                                   "long_term_debt_to_equity_annual": 0.5,
                                   "ten_day_avg_trading_volume": 1_000_000}
        self.sym.fundamentals_updated_at = now()
        self.sym.save()
        call_command("pull_fundamentals", stale_days=7)
        mock_fetch.assert_not_called()

    @patch("screener.services.finnhub_client.fetch_fundamentals")
    def test_handles_api_failure_gracefully(self, mock_fetch):
        mock_fetch.return_value = None
        # Should not raise, should just continue
        call_command("pull_fundamentals")
        self.sym.refresh_from_db()
        self.assertIsNone(self.sym.fundamentals_updated_at)

    @patch("screener.services.finnhub_client.fetch_fundamentals")
    def test_limit_option(self, mock_fetch):
        mock_fetch.return_value = {
            "market_cap": 1_000_000_000, "operating_margin": 0.1,
            "cash_flow_per_share_annual": 1.0, "long_term_debt_to_equity_annual": 0.5,
            "ten_day_avg_trading_volume": 1_000_000,
        }
        # Create 3 symbols, use limit=1
        Symbol.objects.create(ticker="MSFT", exchange_mic="XNAS", name="Microsoft")
        Symbol.objects.create(ticker="GOOG", exchange_mic="XNAS", name="Alphabet")
        call_command("pull_fundamentals", limit=1)
        self.assertEqual(mock_fetch.call_count, 1)
