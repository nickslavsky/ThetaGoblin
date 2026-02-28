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
        # Chain with ATM-bracketing strikes around spot=230
        mock_chain.return_value = [
            {"strike": 225.0, "bid": 2.50, "ask": 2.70,
             "implied_volatility": 0.30, "open_interest": 500,
             "volume": 120, "spot_price": 230.0},
            {"strike": 235.0, "bid": 5.00, "ask": 5.30,
             "implied_volatility": 0.34, "open_interest": 300,
             "volume": 80, "spot_price": 230.0},
        ]
        call_command("pull_options", delay=0)
        self.assertEqual(IV30Snapshot.objects.count(), 1)
        snap = IV30Snapshot.objects.first()
        self.assertAlmostEqual(snap.iv30, 0.32)  # avg of 0.30 and 0.34
        self.assertEqual(snap.symbol, self.sym)

    @patch("screener.management.commands.pull_options.yfinance_svc.get_expiry_dates")
    @patch("screener.management.commands.pull_options.yfinance_svc.get_puts_chain")
    def test_skips_iv30_when_none(self, mock_chain, mock_expiries):
        today = date.today()
        expiry = today + timedelta(days=35)
        mock_expiries.return_value = [expiry.isoformat()]
        # Chain with zero IVs → compute_atm_iv returns None → no IV30Snapshot
        mock_chain.return_value = [
            {"strike": 225.0, "bid": 2.50, "ask": 2.70,
             "implied_volatility": 0.0, "open_interest": 500,
             "volume": 120, "spot_price": 230.0},
        ]
        call_command("pull_options", delay=0)
        self.assertEqual(IV30Snapshot.objects.count(), 0)
