from unittest.mock import patch, MagicMock
from django.test import TestCase
from screener.services import finnhub_client


class FetchFundamentalsTest(TestCase):

    @patch("screener.services.finnhub_client.requests.get")
    def test_parses_valid_response(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "metric": {
                "marketCapitalization": 3000.0,  # in millions
                "operatingMarginAnnual": 0.30,
                "cashFlowPerShareAnnual": 7.5,
                "longTermDebt/equityAnnual": 1.2,
                "10DayAverageTradingVolume": 5_000_000.0,
            }
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = finnhub_client.fetch_fundamentals("AAPL")

        self.assertIsNotNone(result)
        self.assertEqual(result["market_cap"], 3_000_000_000)
        self.assertAlmostEqual(result["operating_margin"], 0.30)
        self.assertAlmostEqual(result["cash_flow_per_share_annual"], 7.5)
        self.assertAlmostEqual(result["long_term_debt_to_equity_annual"], 1.2)
        self.assertAlmostEqual(result["ten_day_avg_trading_volume"], 5_000_000.0)

    @patch("screener.services.finnhub_client.requests.get")
    def test_returns_none_on_http_error(self, mock_get):
        mock_get.side_effect = Exception("Connection timeout")
        result = finnhub_client.fetch_fundamentals("AAPL")
        self.assertIsNone(result)

    @patch("screener.services.finnhub_client.requests.get")
    def test_handles_missing_market_cap(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"metric": {}}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = finnhub_client.fetch_fundamentals("UNKNOWN")
        # Market cap missing — result should be None or have None market_cap
        if result is not None:
            self.assertIsNone(result.get("market_cap"))

    @patch("screener.services.finnhub_client.requests.get")
    def test_fetch_symbols_returns_list(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {"symbol": "AAPL", "description": "Apple Inc", "type": "Common Stock"},
            {"symbol": "MSFT", "description": "Microsoft", "type": "Common Stock"},
        ]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = finnhub_client.fetch_symbols("XNAS")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)

    @patch("screener.services.finnhub_client.requests.get")
    def test_fetch_symbols_returns_empty_on_error(self, mock_get):
        mock_get.side_effect = Exception("Network error")
        result = finnhub_client.fetch_symbols("XNAS")
        self.assertEqual(result, [])
