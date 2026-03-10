from unittest.mock import patch, MagicMock
from django.test import TestCase
from screener.services import finnhub_client


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
