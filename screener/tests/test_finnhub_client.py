from unittest.mock import patch, MagicMock
from django.test import TestCase
from requests.exceptions import ReadTimeout
from screener.services import finnhub_client
from screener.services.finnhub_client import RateLimitError


class FetchEarningsTest(TestCase):

    @patch("screener.services.finnhub_client.requests.get")
    def test_timeout_raises_rate_limit_error(self, mock_get):
        """Timeouts should raise RateLimitError so call_with_backoff retries."""
        mock_get.side_effect = ReadTimeout("Read timed out")
        with self.assertRaises(RateLimitError):
            finnhub_client.fetch_earnings("2026-03-01", "2026-03-07")

    @patch("screener.services.finnhub_client.requests.get")
    def test_returns_earnings_on_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "earningsCalendar": [{"symbol": "AAPL", "date": "2026-04-25"}]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = finnhub_client.fetch_earnings("2026-04-21", "2026-04-27")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["symbol"], "AAPL")


class FetchSymbolsTest(TestCase):

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
