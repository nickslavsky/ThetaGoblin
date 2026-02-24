from datetime import date, timedelta
from django.test import TestCase, Client
from django.urls import reverse
from screener.models import Symbol, OptionsSnapshot, FilterConfig


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

    def test_refresh_post_returns_redirect(self):
        resp = self.client.post("/candidates/refresh/")
        self.assertEqual(resp.status_code, 302)

    def test_refresh_get_returns_redirect(self):
        # GET on refresh should also redirect (not 405)
        resp = self.client.get("/candidates/refresh/")
        self.assertEqual(resp.status_code, 302)

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
