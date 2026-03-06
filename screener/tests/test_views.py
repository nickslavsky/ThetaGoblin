import json
from datetime import date, timedelta
from unittest.mock import patch
from django.test import TestCase, Client
from django.urls import reverse
from screener.models import Symbol, OptionsSnapshot, IVRank, FilterConfig


class CandidatesViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        # Create a qualifying symbol (passes all FilterConfig thresholds)
        self.aapl = Symbol.objects.create(
            ticker="AAPL", exchange_mic="XNAS", name="Apple Inc",
            market_cap=3_000_000_000_000,
            operating_margin=0.30,
            cash_flow_per_share_annual=7.5,
            long_term_debt_to_equity_annual=1.2,
            ten_day_avg_trading_volume=5_000_000,
        )
        # Create a non-qualifying symbol (low market cap)
        self.penny = Symbol.objects.create(
            ticker="PENNY", exchange_mic="XNAS", name="Penny Stock",
            market_cap=100_000_000,  # below 10B threshold
            operating_margin=0.05,
            cash_flow_per_share_annual=0.5,
            long_term_debt_to_equity_annual=0.5,
            ten_day_avg_trading_volume=100_000,
        )
        # Create an options snapshot for AAPL with delta in display band (-0.15 to -0.30)
        today = date.today()
        self.snap = OptionsSnapshot.objects.create(
            symbol=self.aapl,
            snapshot_date=today,
            expiry_date=today + timedelta(days=35),
            dte_at_snapshot=35,
            strike="195.00",
            spot_price="230.00",
            implied_volatility=0.28,
            bid="2.50",
            ask="2.70",
            delta=-0.22,  # in display band
        )

        # Disable notional OI filter by default so existing tests aren't affected
        FilterConfig.objects.update_or_create(
            key="min_notional_oi",
            defaults={"value": "0", "value_type": "int",
                      "description": "Minimum notional open interest"},
        )

    def test_candidates_page_loads(self):
        resp = self.client.get("/candidates/")
        self.assertEqual(resp.status_code, 200)

    def test_candidates_shows_qualifying_ticker(self):
        resp = self.client.get("/candidates/")
        self.assertContains(resp, "AAPL")

    def test_candidates_excludes_non_qualifying(self):
        resp = self.client.get("/candidates/")
        self.assertNotContains(resp, "PENNY")

    def test_root_redirects_to_candidates(self):
        resp = self.client.get("/")
        self.assertIn(resp.status_code, [301, 302])
        self.assertIn("/candidates/", resp["Location"])

    def test_candidates_excludes_ticker_with_only_too_close_strike(self):
        """Symbol whose only option is < 15% OTM should not appear as a candidate."""
        today = date.today()
        tsla = Symbol.objects.create(
            ticker="TSLA", exchange_mic="XNAS", name="Tesla Inc",
            market_cap=1_000_000_000_000,
            operating_margin=0.10,
            cash_flow_per_share_annual=3.0,
            long_term_debt_to_equity_annual=0.5,
            ten_day_avg_trading_volume=5_000_000,
        )
        # strike=220, spot=230 → OTM=4.3%, below otm_pct_min=15%
        OptionsSnapshot.objects.create(
            symbol=tsla,
            snapshot_date=today,
            expiry_date=today + timedelta(days=35),
            dte_at_snapshot=35,
            strike="220.00",
            spot_price="230.00",
            implied_volatility=0.28,
            bid="1.00",
            ask="1.20",
            delta=-0.22,
        )
        resp = self.client.get("/candidates/")
        self.assertNotContains(resp, "TSLA")

    def test_candidates_excludes_ticker_with_only_too_far_strike(self):
        """Symbol whose only option is > 20% OTM should not appear as a candidate."""
        today = date.today()
        meta = Symbol.objects.create(
            ticker="META", exchange_mic="XNAS", name="Meta Platforms",
            market_cap=1_400_000_000_000,
            operating_margin=0.35,
            cash_flow_per_share_annual=12.0,
            long_term_debt_to_equity_annual=0.3,
            ten_day_avg_trading_volume=5_000_000,
        )
        # strike=160, spot=230 → OTM=30.4%, above otm_pct_max=20%
        OptionsSnapshot.objects.create(
            symbol=meta,
            snapshot_date=today,
            expiry_date=today + timedelta(days=35),
            dte_at_snapshot=35,
            strike="160.00",
            spot_price="230.00",
            implied_volatility=0.28,
            bid="0.50",
            ask="0.70",
            delta=-0.22,
        )
        resp = self.client.get("/candidates/")
        self.assertNotContains(resp, "META")

    def test_candidates_shows_iv_rank(self):
        """IV rank badge should appear when IVRank exists."""
        IVRank.objects.create(
            symbol=self.aapl, computed_date=date.today(),
            iv_rank=75.0, iv_percentile=65.0,
            weeks_of_history=30, is_reliable=False,
        )
        resp = self.client.get("/candidates/")
        self.assertContains(resp, "IVR: 75.0")

    def test_candidates_filters_reliable_rank_outside_range(self):
        """Symbol with reliable IV rank outside [70, 90] should be excluded."""
        IVRank.objects.create(
            symbol=self.aapl, computed_date=date.today(),
            iv_rank=50.0, iv_percentile=40.0,
            weeks_of_history=52, is_reliable=True,
        )
        resp = self.client.get("/candidates/")
        self.assertNotContains(resp, "AAPL")

    def test_candidates_keeps_unreliable_rank(self):
        """Symbol with unreliable IV rank outside range should still appear."""
        IVRank.objects.create(
            symbol=self.aapl, computed_date=date.today(),
            iv_rank=50.0, iv_percentile=40.0,
            weeks_of_history=10, is_reliable=False,
        )
        resp = self.client.get("/candidates/")
        self.assertContains(resp, "AAPL")


    def test_candidate_excluded_by_low_notional_oi(self):
        """Symbol with no open interest should be excluded when threshold is set."""
        FilterConfig.objects.filter(key="min_notional_oi").update(value="10000000")
        # AAPL snapshot has open_interest=None → notional_oi=0, below $10M
        resp = self.client.get("/candidates/")
        self.assertNotContains(resp, "AAPL")

    def test_candidate_included_with_sufficient_notional_oi(self):
        """Symbol with enough OI should pass the notional OI filter."""
        FilterConfig.objects.filter(key="min_notional_oi").update(value="10000000")
        # Update AAPL snapshot with high open interest: 60000 * 195 = $11.7M > $10M
        self.snap.open_interest = 60000
        self.snap.save()
        resp = self.client.get("/candidates/")
        self.assertContains(resp, "AAPL")

    def test_notional_oi_displayed(self):
        """NOI badge should render when notional_oi is present."""
        self.snap.open_interest = 60000
        self.snap.save()
        resp = self.client.get("/candidates/")
        self.assertContains(resp, "NOI:")

    def test_suppressed_symbol_hidden_from_view(self):
        """Symbol with suppress_until >= today should not appear in candidates."""
        self.aapl.suppress_until = date.today() + timedelta(days=30)
        self.aapl.save()
        resp = self.client.get("/candidates/")
        self.assertNotContains(resp, "AAPL")


class RefreshCandidatesViewTest(TestCase):

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

    @patch("screener.views.fetch_live_options")
    def test_refresh_renders_directly(self, mock_fetch):
        """Refresh should render the template directly, not redirect."""
        mock_fetch.return_value = []
        resp = self.client.post("/candidates/refresh/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Live data")

    @patch("screener.views.fetch_live_options")
    def test_refresh_does_not_persist_options(self, mock_fetch):
        """After refresh, OptionsSnapshot count should be unchanged."""
        initial_count = OptionsSnapshot.objects.count()
        mock_fetch.return_value = []
        self.client.post("/candidates/refresh/")
        self.assertEqual(OptionsSnapshot.objects.count(), initial_count)

    @patch("screener.views.fetch_live_options")
    def test_refresh_get_also_works(self, mock_fetch):
        """GET on refresh should also work (render live data)."""
        mock_fetch.return_value = []
        resp = self.client.get("/candidates/refresh/")
        self.assertEqual(resp.status_code, 200)


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
