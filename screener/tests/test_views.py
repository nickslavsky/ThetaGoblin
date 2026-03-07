import json
from datetime import date, timedelta
from unittest.mock import patch, Mock
from django.test import TestCase, Client
from screener.models import Symbol, IVRank


class CandidatesShellTest(TestCase):
    """Tests for the candidates shell page (no data fetching)."""

    def setUp(self):
        self.client = Client()

    def test_candidates_page_loads(self):
        resp = self.client.get("/candidates/")
        self.assertEqual(resp.status_code, 200)

    def test_candidates_shell_has_container(self):
        resp = self.client.get("/candidates/")
        self.assertContains(resp, 'id="candidates-container"')

    def test_candidates_shell_has_spinner(self):
        resp = self.client.get("/candidates/")
        self.assertContains(resp, 'id="spinner"')

    def test_candidates_shell_has_refresh_button(self):
        resp = self.client.get("/candidates/")
        self.assertContains(resp, 'id="refresh-btn"')

    def test_root_redirects_to_candidates(self):
        resp = self.client.get("/")
        self.assertIn(resp.status_code, [301, 302])
        self.assertIn("/candidates/", resp["Location"])


class CandidatesStreamTest(TestCase):
    """Tests for the SSE streaming endpoint."""

    def setUp(self):
        self.client = Client()
        self.aapl = Symbol.objects.create(
            ticker="AAPL", exchange_mic="XNAS", name="Apple Inc",
            market_cap=3_000_000_000_000,
            operating_margin=0.30,
            cash_flow_per_share_annual=7.5,
            long_term_debt_to_equity_annual=1.2,
            ten_day_avg_trading_volume=5_000_000,
        )

    @patch("screener.views.stream_live_candidates")
    def test_stream_returns_sse_content_type(self, mock_gen):
        mock_gen.return_value = iter([])
        resp = self.client.get("/candidates/stream/")
        self.assertEqual(resp["Content-Type"], "text/event-stream")

    @patch("screener.views.stream_live_candidates")
    def test_stream_yields_candidate_events(self, mock_gen):
        candidate = {
            "symbol": self.aapl,
            "spot": 230.0,
            "options": [
                {"expiry": date.today() + timedelta(days=35), "dte": 35,
                 "strike": 195.0, "otm_pct": 15.2, "bid": 2.50,
                 "ask": 2.70, "delta": -0.22, "iv": 28.0},
            ],
            "iv_rank": 75.0,
            "iv_rank_reliable": True,
            "notional_oi": "$11,700,000",
        }
        mock_gen.return_value = iter([candidate])
        resp = self.client.get("/candidates/stream/")
        content = b"".join(resp.streaming_content).decode()
        self.assertIn("event: candidate", content)
        self.assertIn("AAPL", content)

    @patch("screener.views.stream_live_candidates")
    def test_stream_ends_with_done_event(self, mock_gen):
        mock_gen.return_value = iter([])
        resp = self.client.get("/candidates/stream/")
        content = b"".join(resp.streaming_content).decode()
        self.assertIn("event: done", content)
        self.assertIn("data: 0", content)

    @patch("screener.views.stream_live_candidates")
    def test_stream_done_count_matches(self, mock_gen):
        candidates = [
            {"symbol": self.aapl, "spot": 230.0, "options": [],
             "iv_rank": None, "iv_rank_reliable": None, "notional_oi": "$0"},
        ]
        mock_gen.return_value = iter(candidates)
        resp = self.client.get("/candidates/stream/")
        content = b"".join(resp.streaming_content).decode()
        self.assertIn("data: 1", content)

    @patch("screener.views.stream_live_candidates")
    def test_stream_no_cache_header(self, mock_gen):
        mock_gen.return_value = iter([])
        resp = self.client.get("/candidates/stream/")
        self.assertEqual(resp["Cache-Control"], "no-cache")


class SuppressViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.aapl = Symbol.objects.create(
            ticker="AAPL", exchange_mic="XNAS", name="Apple Inc",
            market_cap=3_000_000_000_000,
            operating_margin=0.30,
            cash_flow_per_share_annual=7.5,
            long_term_debt_to_equity_annual=1.2,
            ten_day_avg_trading_volume=5_000_000,
        )

    def test_suppress_sets_date(self):
        resp = self.client.post(
            "/candidates/suppress/",
            data=json.dumps({"symbol_id": self.aapl.pk, "suppress_until": "2026-04-18"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.aapl.refresh_from_db()
        self.assertEqual(self.aapl.suppress_until, date(2026, 4, 18))

    def test_suppress_returns_json(self):
        resp = self.client.post(
            "/candidates/suppress/",
            data=json.dumps({"symbol_id": self.aapl.pk, "suppress_until": "2026-04-18"}),
            content_type="application/json",
        )
        self.assertEqual(resp["Content-Type"], "application/json")
        body = resp.json()
        self.assertEqual(body["status"], "ok")

    def test_suppress_rejects_get(self):
        resp = self.client.get("/candidates/suppress/")
        self.assertEqual(resp.status_code, 405)

    def test_suppress_missing_symbol_returns_404(self):
        resp = self.client.post(
            "/candidates/suppress/",
            data=json.dumps({"symbol_id": 99999, "suppress_until": "2026-04-18"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 404)
