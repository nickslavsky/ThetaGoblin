from datetime import date, timedelta
from unittest.mock import patch
from django.test import TestCase
from django.core.management import call_command
from screener.models import Symbol, IV30Snapshot, OptionsSnapshot


class PullOptionsTest(TestCase):

    def setUp(self):
        self.sym = Symbol.objects.create(
            ticker="AAPL", exchange_mic="XNAS", name="Apple Inc",
            market_cap=3_000_000_000_000,
            operating_margin=0.30,
            cash_flow_per_share_annual=7.5,
            long_term_debt_to_equity_annual=1.2,
            ten_day_avg_trading_volume=5_000_000,
        )

    @patch("screener.management.commands.pull_options.yfinance_svc.get_expiry_dates")
    @patch("screener.management.commands.pull_options.yfinance_svc.get_puts_chain")
    def test_saves_options_snapshot(self, mock_chain, mock_expiries):
        today = date.today()
        expiry = today + timedelta(days=35)
        mock_expiries.return_value = [expiry.isoformat()]
        mock_chain.return_value = [{
            "strike": 215.0, "bid": 2.50, "ask": 2.70,
            "implied_volatility": 0.28, "open_interest": 500,
            "volume": 120, "spot_price": 230.0,
        }]
        call_command("pull_options", delay=0)
        self.assertGreater(OptionsSnapshot.objects.filter(symbol=self.sym).count(), 0)

    @patch("screener.management.commands.pull_options.yfinance_svc.get_expiry_dates")
    @patch("screener.management.commands.pull_options.yfinance_svc.get_puts_chain")
    def test_skips_expiries_outside_dte_window(self, mock_chain, mock_expiries):
        today = date.today()
        mock_expiries.return_value = [(today + timedelta(days=5)).isoformat()]
        mock_chain.return_value = []
        call_command("pull_options", delay=0)
        mock_chain.assert_not_called()

    @patch("screener.management.commands.pull_options.yfinance_svc.get_expiry_dates")
    @patch("screener.management.commands.pull_options.yfinance_svc.get_puts_chain")
    def test_handles_yfinance_failure_gracefully(self, mock_chain, mock_expiries):
        today = date.today()
        mock_expiries.return_value = [(today + timedelta(days=35)).isoformat()]
        mock_chain.return_value = None
        call_command("pull_options", delay=0)
        self.assertEqual(OptionsSnapshot.objects.count(), 0)

    @patch("screener.management.commands.pull_options.yfinance_svc.get_expiry_dates")
    @patch("screener.management.commands.pull_options.yfinance_svc.get_puts_chain")
    def test_stores_iv30_snapshot(self, mock_chain, mock_expiries):
        today = date.today()
        expiry = today + timedelta(days=35)
        mock_expiries.return_value = [expiry.isoformat()]

        def chain_with_iv30(ticker, expiry_str, *, ticker_info=None):
            if ticker_info is not None:
                ticker_info["iv30"] = 0.32
                ticker_info["spot_price"] = 230.0
            return [{
                "strike": 215.0, "bid": 2.50, "ask": 2.70,
                "implied_volatility": 0.28, "open_interest": 500,
                "volume": 120, "spot_price": 230.0,
            }]

        mock_chain.side_effect = chain_with_iv30
        call_command("pull_options", delay=0)
        self.assertEqual(IV30Snapshot.objects.count(), 1)
        snap = IV30Snapshot.objects.first()
        self.assertAlmostEqual(snap.iv30, 0.32)
        self.assertEqual(snap.symbol, self.sym)

    @patch("screener.management.commands.pull_options.yfinance_svc.get_expiry_dates")
    @patch("screener.management.commands.pull_options.yfinance_svc.get_puts_chain")
    def test_skips_iv30_when_none(self, mock_chain, mock_expiries):
        today = date.today()
        expiry = today + timedelta(days=35)
        mock_expiries.return_value = [expiry.isoformat()]

        def chain_no_iv30(ticker, expiry_str, *, ticker_info=None):
            if ticker_info is not None:
                ticker_info["iv30"] = None
                ticker_info["spot_price"] = 230.0
            return [{
                "strike": 215.0, "bid": 2.50, "ask": 2.70,
                "implied_volatility": 0.28, "open_interest": 500,
                "volume": 120, "spot_price": 230.0,
            }]

        mock_chain.side_effect = chain_no_iv30
        call_command("pull_options", delay=0)
        self.assertEqual(IV30Snapshot.objects.count(), 0)
