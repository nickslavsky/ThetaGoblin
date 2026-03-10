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

    @patch("screener.services.yfinance_svc.yf.Ticker")
    def test_get_puts_chain_handles_nan_volume_and_open_interest(self, mock_ticker_cls):
        """yfinance returns NaN for volume/openInterest on illiquid strikes — must not crash."""
        mock_ticker = MagicMock()
        mock_ticker.info = {"currentPrice": 50.0}
        puts_df = pd.DataFrame([
            {"strike": 45.0, "bid": 0.10, "ask": 0.15,
             "impliedVolatility": 0.35, "openInterest": float("nan"), "volume": float("nan")},
        ])
        mock_chain = MagicMock()
        mock_chain.puts = puts_df
        mock_ticker.option_chain.return_value = mock_chain
        mock_ticker_cls.return_value = mock_ticker

        result = yfinance_svc.get_puts_chain("AA", "2026-03-27")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["volume"], 0)
        self.assertEqual(result[0]["open_interest"], 0)


from screener.services.yfinance_svc import fetch_fundamentals, YFinanceError


class FetchFundamentalsTest(TestCase):

    @patch("screener.services.yfinance_svc.yf.Ticker")
    def test_returns_correct_fields(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "marketCap": 3_835_868_741_632,
            "operatingMargins": 0.35374,
            "freeCashflow": 106_312_753_152,
            "debtToEquity": 102.63,
            "averageVolume10days": 43_457_250,
        }
        mock_ticker_cls.return_value = mock_ticker

        result = fetch_fundamentals("AAPL")

        self.assertEqual(result["market_cap"], 3_835_868_741_632)
        self.assertAlmostEqual(result["operating_margin"], 0.35374)
        self.assertEqual(result["free_cash_flow"], 106_312_753_152)
        self.assertAlmostEqual(result["debt_to_equity"], 102.63)
        self.assertEqual(result["avg_volume_10d"], 43_457_250)

    @patch("screener.services.yfinance_svc.yf.Ticker")
    def test_handles_missing_fields_gracefully(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.info = {"marketCap": 1_000_000_000}
        mock_ticker_cls.return_value = mock_ticker

        result = fetch_fundamentals("XYZ")

        self.assertEqual(result["market_cap"], 1_000_000_000)
        self.assertIsNone(result["operating_margin"])
        self.assertIsNone(result["free_cash_flow"])
        self.assertIsNone(result["debt_to_equity"])
        self.assertIsNone(result["avg_volume_10d"])

    @patch("screener.services.yfinance_svc.yf.Ticker")
    def test_raises_yfinance_error_on_exception(self, mock_ticker_cls):
        mock_ticker_cls.side_effect = Exception("network timeout")

        with self.assertRaises(YFinanceError):
            fetch_fundamentals("AAPL")

    @patch("screener.services.yfinance_svc.yf.Ticker")
    def test_raises_yfinance_error_on_empty_info(self, mock_ticker_cls):
        """yfinance returns empty dict when ticker is delisted/invalid."""
        mock_ticker = MagicMock()
        mock_ticker.info = {}
        mock_ticker_cls.return_value = mock_ticker

        with self.assertRaises(YFinanceError):
            fetch_fundamentals("INVALID")
