import json
from http.client import HTTPResponse
from io import BytesIO
from unittest.mock import MagicMock, patch

from django.test import TestCase

from screener.services.dolthub_client import (
    DoltHubError,
    _execute_query,
    fetch_iv_rows,
    fetch_latest_date,
)


def _mock_response(body: dict, status: int = 200) -> MagicMock:
    """Build a mock that quacks like urllib's HTTPResponse."""
    data = json.dumps(body).encode()
    resp = MagicMock(spec=HTTPResponse)
    resp.status = status
    resp.read.return_value = data
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


class FetchIvRowsTest(TestCase):
    """Tests for fetch_iv_rows()."""

    @patch("screener.services.dolthub_client.urlopen")
    def test_parses_successful_response(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response({
            "query_execution_status": "Success",
            "rows": [
                {"date": "2026-03-03", "act_symbol": "AAPL", "iv_current": "0.2828"},
                {"date": "2026-03-03", "act_symbol": "MSFT", "iv_current": "0.1950"},
            ],
            "schema": [],
        })

        rows = fetch_iv_rows("2026-03-01", "2026-03-04")

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["act_symbol"], "AAPL")
        self.assertEqual(rows[0]["iv_current"], "0.2828")
        self.assertEqual(rows[1]["act_symbol"], "MSFT")

    @patch("screener.services.dolthub_client.urlopen")
    def test_returns_empty_on_api_error_status(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response({
            "query_execution_status": "Error",
            "rows": [],
            "schema": [],
        })

        rows = fetch_iv_rows("2026-03-01", "2026-03-04")
        self.assertEqual(rows, [])

    @patch("screener.services.dolthub_client.urlopen")
    def test_raises_dolthub_error_on_network_error(self, mock_urlopen):
        mock_urlopen.side_effect = OSError("Connection refused")

        with self.assertRaises(DoltHubError):
            fetch_iv_rows("2026-03-01", "2026-03-04")

    @patch("screener.services.dolthub_client.urlopen")
    def test_builds_sql_with_symbol_range(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response({
            "query_execution_status": "Success",
            "rows": [],
            "schema": [],
        })

        fetch_iv_rows("2026-03-01", "2026-03-04", sym_min="A", sym_max="D")

        # Verify the URL contains the symbol range conditions
        call_args = mock_urlopen.call_args
        req_obj = call_args[0][0]
        url = req_obj.full_url if hasattr(req_obj, "full_url") else str(req_obj)
        self.assertIn("act_symbol%20%3E%3D%20%27A%27", url)
        self.assertIn("act_symbol%20%3C%20%27D%27", url)

    @patch("screener.services.dolthub_client.urlopen")
    def test_logs_debug_messages(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response({
            "query_execution_status": "Success",
            "rows": [
                {"date": "2026-03-03", "act_symbol": "AAPL", "iv_current": "0.28"},
            ],
            "schema": [],
        })

        with self.assertLogs("screener.services.dolthub_client", level="DEBUG") as cm:
            fetch_iv_rows("2026-03-01", "2026-03-04")

        log_text = "\n".join(cm.output)
        self.assertIn("SQL", log_text)
        self.assertIn("rows", log_text.lower())


class FetchLatestDateTest(TestCase):
    """Tests for fetch_latest_date()."""

    @patch("screener.services.dolthub_client.urlopen")
    def test_returns_date_string(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response({
            "query_execution_status": "Success",
            "rows": [{"latest": "2026-03-03"}],
            "schema": [],
        })

        result = fetch_latest_date()
        self.assertEqual(result, "2026-03-03")

    @patch("screener.services.dolthub_client.urlopen")
    def test_raises_dolthub_error_on_network_error(self, mock_urlopen):
        mock_urlopen.side_effect = OSError("timeout")

        with self.assertRaises(DoltHubError):
            fetch_latest_date()

    @patch("screener.services.dolthub_client.urlopen")
    def test_returns_none_on_empty_rows(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response({
            "query_execution_status": "Success",
            "rows": [],
            "schema": [],
        })

        result = fetch_latest_date()
        self.assertIsNone(result)


class ExecuteQueryTest(TestCase):
    """Tests for _execute_query() low-level function."""

    @patch("screener.services.dolthub_client.urlopen")
    def test_raises_dolthub_error_on_429(self, mock_urlopen):
        from urllib.error import HTTPError

        mock_urlopen.side_effect = HTTPError(
            url="https://example.com",
            code=429,
            msg="Too Many Requests",
            hdrs={},
            fp=BytesIO(b"rate limited"),
        )

        with self.assertRaises(DoltHubError) as ctx:
            _execute_query("SELECT 1")
        self.assertIn("429", str(ctx.exception))

    @patch("screener.services.dolthub_client.urlopen")
    def test_raises_dolthub_error_on_500(self, mock_urlopen):
        from urllib.error import HTTPError

        mock_urlopen.side_effect = HTTPError(
            url="https://example.com",
            code=500,
            msg="Internal Server Error",
            hdrs={},
            fp=BytesIO(b"server error"),
        )

        with self.assertRaises(DoltHubError) as ctx:
            _execute_query("SELECT 1")
        self.assertIn("500", str(ctx.exception))

    @patch("screener.services.dolthub_client.urlopen")
    def test_returns_parsed_json_on_success(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response({
            "query_execution_status": "Success",
            "rows": [{"col": "val"}],
            "schema": [],
        })

        result = _execute_query("SELECT col FROM t")
        self.assertEqual(result["query_execution_status"], "Success")
        self.assertEqual(len(result["rows"]), 1)

    @patch("screener.services.dolthub_client.urlopen")
    def test_raises_dolthub_error_on_network_timeout(self, mock_urlopen):
        mock_urlopen.side_effect = OSError("Connection timed out")

        with self.assertRaises(DoltHubError) as ctx:
            _execute_query("SELECT 1")
        self.assertIn("network error", str(ctx.exception))
