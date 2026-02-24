from datetime import date, timedelta
from unittest.mock import patch
from django.test import TestCase
from screener.models import Symbol, OptionsSnapshot
from screener.services.live_options import fetch_live_options


class FetchLiveOptionsTest(TestCase):

    def setUp(self):
        self.sym = Symbol.objects.create(
            ticker="AAPL", exchange_mic="XNAS", name="Apple Inc",
            market_cap=3_000_000_000_000,
            operating_margin=0.30,
            cash_flow_per_share_annual=7.5,
            long_term_debt_to_equity_annual=1.2,
            ten_day_avg_trading_volume=5_000_000,
        )
        self.cfg = {
            "expiry_dte_min": 30,
            "expiry_dte_max": 45,
            "risk_free_rate": 0.043,
            "delta_target_min": 0.15,
            "delta_target_max": 0.30,
            "otm_pct_min": 0.15,
            "otm_pct_max": 0.20,
        }
        today = date.today()
        self.expiry = today + timedelta(days=35)

    @patch("screener.services.live_options.yfinance_svc.get_expiry_dates")
    @patch("screener.services.live_options.yfinance_svc.get_puts_chain")
    def test_returns_correct_structure(self, mock_chain, mock_expiries):
        mock_expiries.return_value = [self.expiry.isoformat()]
        # vol=0.80 gives delta≈-0.21 for 195/230 at 35 DTE (in display band)
        mock_chain.return_value = [{
            "strike": 195.0, "bid": 2.50, "ask": 2.70,
            "implied_volatility": 0.80, "open_interest": 500,
            "volume": 120, "spot_price": 230.0,
        }]

        result = fetch_live_options([self.sym], self.cfg)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["symbol"], self.sym)
        self.assertEqual(result[0]["spot"], 230.0)
        self.assertGreater(len(result[0]["options"]), 0)
        opt = result[0]["options"][0]
        self.assertIn("expiry", opt)
        self.assertIn("strike", opt)
        self.assertIn("delta", opt)

    @patch("screener.services.live_options.yfinance_svc.get_expiry_dates")
    @patch("screener.services.live_options.yfinance_svc.get_puts_chain")
    def test_no_db_writes(self, mock_chain, mock_expiries):
        mock_expiries.return_value = [self.expiry.isoformat()]
        mock_chain.return_value = [{
            "strike": 195.0, "bid": 2.50, "ask": 2.70,
            "implied_volatility": 0.80, "open_interest": 500,
            "volume": 120, "spot_price": 230.0,
        }]

        fetch_live_options([self.sym], self.cfg)
        self.assertEqual(OptionsSnapshot.objects.count(), 0)

    @patch("screener.services.live_options.yfinance_svc.get_expiry_dates")
    @patch("screener.services.live_options.yfinance_svc.get_puts_chain")
    def test_filters_by_dte(self, mock_chain, mock_expiries):
        """Expiry outside DTE window should be excluded."""
        too_soon = (date.today() + timedelta(days=5)).isoformat()
        mock_expiries.return_value = [too_soon]
        mock_chain.return_value = [{
            "strike": 195.0, "bid": 2.50, "ask": 2.70,
            "implied_volatility": 0.28, "open_interest": 500,
            "volume": 120, "spot_price": 230.0,
        }]

        result = fetch_live_options([self.sym], self.cfg)
        self.assertEqual(len(result), 0)
        mock_chain.assert_not_called()

    @patch("screener.services.live_options.yfinance_svc.get_expiry_dates")
    @patch("screener.services.live_options.yfinance_svc.get_puts_chain")
    def test_filters_otm_range(self, mock_chain, mock_expiries):
        """Strikes outside OTM% range should be excluded."""
        mock_expiries.return_value = [self.expiry.isoformat()]
        # strike=220, spot=230 → OTM=4.3%, below 15% min
        mock_chain.return_value = [{
            "strike": 220.0, "bid": 2.50, "ask": 2.70,
            "implied_volatility": 0.28, "open_interest": 500,
            "volume": 120, "spot_price": 230.0,
        }]

        result = fetch_live_options([self.sym], self.cfg)
        self.assertEqual(len(result), 0)
