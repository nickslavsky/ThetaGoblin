from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
from django.test import TestCase

from screener.services.yfinance_svc import fetch_iv30, YFinanceError


class FetchIV30Test(TestCase):

    def _mock_chain(self, puts_data, calls_data, spot=None):
        """Helper to build a mock option_chain return value."""
        mock = MagicMock()
        mock.puts = pd.DataFrame(puts_data)
        mock.calls = pd.DataFrame(calls_data)
        mock.underlying = {"regularMarketPrice": spot} if spot else {}
        return mock

    @staticmethod
    def _setup_mock_date(mock_date, today_date):
        """Configure mock date so today() is controlled but fromisoformat() works."""
        mock_date.today.return_value = today_date
        mock_date.fromisoformat = date.fromisoformat

    @patch("screener.services.yfinance_svc.date")
    @patch("screener.services.yfinance_svc.yf.Ticker")
    def test_returns_atm_average_iv(self, mock_ticker_cls, mock_date):
        """IV30 = average of ATM put IV and ATM call IV."""
        self._setup_mock_date(mock_date, date(2026, 3, 10))
        mock_ticker = MagicMock()
        # 2026-04-17 is 3rd Friday of April, 38 DTE from Mar 10
        mock_ticker.options = ("2026-03-13", "2026-03-20", "2026-04-17", "2026-05-15")
        mock_ticker.option_chain.return_value = self._mock_chain(
            puts_data=[
                {"strike": 225.0, "impliedVolatility": 0.30},
                {"strike": 230.0, "impliedVolatility": 0.28},
                {"strike": 235.0, "impliedVolatility": 0.26},
            ],
            calls_data=[
                {"strike": 225.0, "impliedVolatility": 0.24},
                {"strike": 230.0, "impliedVolatility": 0.26},
                {"strike": 235.0, "impliedVolatility": 0.28},
            ],
            spot=230.0,
        )
        mock_ticker_cls.return_value = mock_ticker

        result = fetch_iv30("AAPL")

        # ATM strike = 230, put IV = 0.28, call IV = 0.26 -> avg = 0.27
        self.assertAlmostEqual(result, 0.27, places=4)
        mock_ticker.option_chain.assert_called_once_with("2026-04-17")

    @patch("screener.services.yfinance_svc.date")
    @patch("screener.services.yfinance_svc.yf.Ticker")
    def test_skips_weeklies_uses_monthly(self, mock_ticker_cls, mock_date):
        """Should skip weekly expiries and use only monthlies."""
        self._setup_mock_date(mock_date, date(2026, 3, 10))
        mock_ticker = MagicMock()
        # 2026-03-13 = weekly (not 3rd Friday), 2026-03-20 = 3rd Fri of March but only 10 DTE
        # 2026-04-17 = 3rd Fri of April, 38 DTE -> this should be selected
        mock_ticker.options = ("2026-03-13", "2026-03-20", "2026-04-17")
        mock_ticker.option_chain.return_value = self._mock_chain(
            puts_data=[{"strike": 100.0, "impliedVolatility": 0.35}],
            calls_data=[{"strike": 100.0, "impliedVolatility": 0.33}],
            spot=100.0,
        )
        mock_ticker_cls.return_value = mock_ticker

        result = fetch_iv30("TEST")

        self.assertAlmostEqual(result, 0.34, places=4)
        mock_ticker.option_chain.assert_called_once_with("2026-04-17")

    @patch("screener.services.yfinance_svc.date")
    @patch("screener.services.yfinance_svc.yf.Ticker")
    def test_picks_closest_strike_to_spot(self, mock_ticker_cls, mock_date):
        """ATM strike = the one closest to spot price."""
        self._setup_mock_date(mock_date, date(2026, 3, 10))
        mock_ticker = MagicMock()
        mock_ticker.options = ("2026-04-17",)
        mock_ticker.option_chain.return_value = self._mock_chain(
            puts_data=[
                {"strike": 145.0, "impliedVolatility": 0.40},
                {"strike": 150.0, "impliedVolatility": 0.35},
                {"strike": 155.0, "impliedVolatility": 0.30},
            ],
            calls_data=[
                {"strike": 145.0, "impliedVolatility": 0.25},
                {"strike": 150.0, "impliedVolatility": 0.30},
                {"strike": 155.0, "impliedVolatility": 0.35},
            ],
            spot=152.0,
        )
        mock_ticker_cls.return_value = mock_ticker

        result = fetch_iv30("TEST")

        # Closest to 152 is 150
        # put IV at 150 = 0.35, call IV at 150 = 0.30 -> avg = 0.325
        self.assertAlmostEqual(result, 0.325, places=4)

    @patch("screener.services.yfinance_svc.date")
    @patch("screener.services.yfinance_svc.yf.Ticker")
    def test_raises_when_no_monthly_with_min_dte(self, mock_ticker_cls, mock_date):
        """Should raise YFinanceError when no monthly has >= 20 DTE."""
        self._setup_mock_date(mock_date, date(2026, 3, 10))
        mock_ticker = MagicMock()
        # Only weekly expiries, no monthly with >= 20 DTE
        mock_ticker.options = ("2026-03-13", "2026-03-20", "2026-03-27")
        mock_ticker_cls.return_value = mock_ticker

        with self.assertRaises(YFinanceError):
            fetch_iv30("TEST")

    @patch("screener.services.yfinance_svc.date")
    @patch("screener.services.yfinance_svc.yf.Ticker")
    def test_raises_when_no_options(self, mock_ticker_cls, mock_date):
        """Should raise YFinanceError when ticker has no options."""
        self._setup_mock_date(mock_date, date(2026, 3, 10))
        mock_ticker = MagicMock()
        mock_ticker.options = ()
        mock_ticker_cls.return_value = mock_ticker

        with self.assertRaises(YFinanceError):
            fetch_iv30("TEST")

    @patch("screener.services.yfinance_svc.yf.Ticker")
    def test_raises_on_yfinance_exception(self, mock_ticker_cls):
        """Network errors should raise YFinanceError for backoff retry."""
        mock_ticker_cls.side_effect = Exception("connection refused")

        with self.assertRaises(YFinanceError):
            fetch_iv30("TEST")

    @patch("screener.services.yfinance_svc.date")
    @patch("screener.services.yfinance_svc.yf.Ticker")
    def test_handles_missing_strike_in_one_side(self, mock_ticker_cls, mock_date):
        """If ATM strike exists only on one side, use that side's IV."""
        self._setup_mock_date(mock_date, date(2026, 3, 10))
        mock_ticker = MagicMock()
        mock_ticker.options = ("2026-04-17",)
        mock_ticker.option_chain.return_value = self._mock_chain(
            puts_data=[{"strike": 100.0, "impliedVolatility": 0.30}],
            calls_data=[{"strike": 95.0, "impliedVolatility": 0.28}],
            spot=100.0,
        )
        mock_ticker_cls.return_value = mock_ticker

        result = fetch_iv30("TEST")

        # Puts: ATM at 100 -> IV=0.30. Calls: closest is 95 -> IV=0.28
        # Each side picks its own closest-to-spot strike
        # Put ATM=100 (IV=0.30), Call ATM=95 (IV=0.28) -> avg=0.29
        self.assertAlmostEqual(result, 0.29, places=4)
