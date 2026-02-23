from unittest.mock import MagicMock, patch
import pandas as pd
from django.test import TestCase
from screener.services import yfinance_svc


class YfinanceSvcTest(TestCase):

    @patch("screener.services.yfinance_svc.yf.Ticker")
    def test_get_expiry_dates_returns_list(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.options = ("2026-03-21", "2026-04-17", "2026-05-15")
        mock_ticker_cls.return_value = mock_ticker
        result = yfinance_svc.get_expiry_dates("AAPL")
        self.assertEqual(result, ["2026-03-21", "2026-04-17", "2026-05-15"])

    @patch("screener.services.yfinance_svc.yf.Ticker")
    def test_get_expiry_dates_returns_empty_on_error(self, mock_ticker_cls):
        mock_ticker_cls.side_effect = Exception("network error")
        result = yfinance_svc.get_expiry_dates("AAPL")
        self.assertEqual(result, [])

    @patch("screener.services.yfinance_svc.yf.Ticker")
    def test_get_puts_chain_returns_list_of_dicts(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.info = {"currentPrice": 230.0}
        puts_df = pd.DataFrame([
            {"strike": 210.0, "bid": 1.50, "ask": 1.70,
             "impliedVolatility": 0.28, "openInterest": 500, "volume": 120},
        ])
        mock_chain = MagicMock()
        mock_chain.puts = puts_df
        mock_ticker.option_chain.return_value = mock_chain
        mock_ticker_cls.return_value = mock_ticker

        result = yfinance_svc.get_puts_chain("AAPL", "2026-03-21")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertIn("strike", result[0])
        self.assertIn("spot_price", result[0])
        self.assertEqual(result[0]["spot_price"], 230.0)

    @patch("screener.services.yfinance_svc.yf.Ticker")
    def test_get_puts_chain_returns_none_on_error(self, mock_ticker_cls):
        mock_ticker_cls.side_effect = Exception("network error")
        result = yfinance_svc.get_puts_chain("AAPL", "2026-03-21")
        self.assertIsNone(result)
