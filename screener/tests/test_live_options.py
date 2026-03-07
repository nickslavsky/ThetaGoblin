from datetime import date, timedelta
from unittest.mock import patch, Mock
from django.test import TestCase
from screener.models import Symbol
from screener.services.live_options import stream_live_candidates


class StreamLiveCandidatesTest(TestCase):

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
            "min_notional_oi": 0,
        }
        today = date.today()
        self.expiry = today + timedelta(days=35)

    @patch("screener.services.live_options.yfinance_svc.get_expiry_dates")
    @patch("screener.services.live_options.yfinance_svc.get_puts_chain")
    def test_returns_correct_structure(self, mock_chain, mock_expiries):
        mock_expiries.return_value = [self.expiry.isoformat()]
        mock_chain.return_value = [{
            "strike": 195.0, "bid": 2.50, "ask": 2.70,
            "implied_volatility": 0.80, "open_interest": 500,
            "volume": 120, "spot_price": 230.0,
        }]

        result = list(stream_live_candidates([self.sym], self.cfg))
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
    def test_filters_by_dte(self, mock_chain, mock_expiries):
        """Expiry outside DTE window should be excluded."""
        too_soon = (date.today() + timedelta(days=5)).isoformat()
        mock_expiries.return_value = [too_soon]
        mock_chain.return_value = [{
            "strike": 195.0, "bid": 2.50, "ask": 2.70,
            "implied_volatility": 0.28, "open_interest": 500,
            "volume": 120, "spot_price": 230.0,
        }]

        result = list(stream_live_candidates([self.sym], self.cfg))
        self.assertEqual(len(result), 0)
        mock_chain.assert_not_called()

    @patch("screener.services.live_options.yfinance_svc.get_expiry_dates")
    @patch("screener.services.live_options.yfinance_svc.get_puts_chain")
    def test_filters_otm_range(self, mock_chain, mock_expiries):
        """Strikes outside OTM% range should be excluded."""
        mock_expiries.return_value = [self.expiry.isoformat()]
        mock_chain.return_value = [{
            "strike": 220.0, "bid": 2.50, "ask": 2.70,
            "implied_volatility": 0.28, "open_interest": 500,
            "volume": 120, "spot_price": 230.0,
        }]

        result = list(stream_live_candidates([self.sym], self.cfg))
        self.assertEqual(len(result), 0)

    @patch("screener.services.live_options.yfinance_svc.get_expiry_dates")
    @patch("screener.services.live_options.yfinance_svc.get_puts_chain")
    def test_includes_iv_rank(self, mock_chain, mock_expiries):
        """Yielded candidate should include iv_rank from pre-fetched iv_ranks dict."""
        mock_expiries.return_value = [self.expiry.isoformat()]
        mock_chain.return_value = [{
            "strike": 195.0, "bid": 2.50, "ask": 2.70,
            "implied_volatility": 0.80, "open_interest": 500,
            "volume": 120, "spot_price": 230.0,
        }]

        mock_rank = Mock(iv_rank=75.3, is_reliable=True)
        iv_ranks = {self.sym.pk: mock_rank}

        result = list(stream_live_candidates([self.sym], self.cfg, iv_ranks=iv_ranks))
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0]["iv_rank"], 75.3)
        self.assertTrue(result[0]["iv_rank_reliable"])

    @patch("screener.services.live_options.yfinance_svc.get_expiry_dates")
    @patch("screener.services.live_options.yfinance_svc.get_puts_chain")
    def test_iv_rank_none_without_data(self, mock_chain, mock_expiries):
        """iv_rank should be None when iv_ranks dict has no entry for symbol."""
        mock_expiries.return_value = [self.expiry.isoformat()]
        mock_chain.return_value = [{
            "strike": 195.0, "bid": 2.50, "ask": 2.70,
            "implied_volatility": 0.80, "open_interest": 500,
            "volume": 120, "spot_price": 230.0,
        }]

        result = list(stream_live_candidates([self.sym], self.cfg))
        self.assertEqual(len(result), 1)
        self.assertIsNone(result[0]["iv_rank"])
        self.assertIsNone(result[0]["iv_rank_reliable"])

    @patch("screener.services.live_options.yfinance_svc.get_expiry_dates")
    def test_continues_on_yfinance_error(self, mock_expiries):
        """Network failure on one symbol should not abort the stream."""
        mock_expiries.side_effect = Exception("network error")
        result = list(stream_live_candidates([self.sym], self.cfg))
        self.assertEqual(len(result), 0)
