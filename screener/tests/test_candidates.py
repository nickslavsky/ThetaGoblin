from datetime import date, timedelta
from django.test import TestCase
from screener.models import FilterConfig, IVRank, Symbol
from screener.services.candidates import get_qualifying_symbols


class IVRankFilterTest(TestCase):
    """Tests for IV rank filtering in get_qualifying_symbols()."""

    def setUp(self):
        self.sym = Symbol.objects.create(
            ticker="AAPL", exchange_mic="XNAS", name="Apple Inc",
            market_cap=3_000_000_000_000,
            operating_margin=0.30,
            free_cash_flow=106_000_000_000,
            debt_to_equity=120.0,
            avg_volume_10d=5_000_000,
        )

    def test_excludes_reliable_iv_rank_below_min(self):
        IVRank.objects.create(
            symbol=self.sym, computed_date=date.today(),
            iv_rank=50.0, weeks_of_history=52, is_reliable=True,
        )
        result = get_qualifying_symbols()
        self.assertNotIn(self.sym, result)

    def test_excludes_reliable_iv_rank_above_max(self):
        IVRank.objects.create(
            symbol=self.sym, computed_date=date.today(),
            iv_rank=95.0, weeks_of_history=52, is_reliable=True,
        )
        result = get_qualifying_symbols()
        self.assertNotIn(self.sym, result)

    def test_includes_reliable_iv_rank_in_range(self):
        IVRank.objects.create(
            symbol=self.sym, computed_date=date.today(),
            iv_rank=75.0, weeks_of_history=52, is_reliable=True,
        )
        result = get_qualifying_symbols()
        self.assertIn(self.sym, result)

    def test_includes_unreliable_iv_rank_outside_range(self):
        IVRank.objects.create(
            symbol=self.sym, computed_date=date.today(),
            iv_rank=50.0, weeks_of_history=10, is_reliable=False,
        )
        result = get_qualifying_symbols()
        self.assertIn(self.sym, result)

    def test_includes_symbol_without_iv_rank(self):
        result = get_qualifying_symbols()
        self.assertIn(self.sym, result)


class SuppressUntilFilterTest(TestCase):
    """Tests for suppress_until filtering in get_qualifying_symbols()."""

    def setUp(self):
        self.sym = Symbol.objects.create(
            ticker="MSFT", exchange_mic="XNAS", name="Microsoft Corp",
            market_cap=3_000_000_000_000,
            operating_margin=0.40,
            free_cash_flow=150_000_000_000,
            debt_to_equity=80.0,
            avg_volume_10d=5_000_000,
        )

    def test_suppressed_today_excluded(self):
        """Symbol with suppress_until == today should NOT appear."""
        self.sym.suppress_until = date.today()
        self.sym.save()
        result = get_qualifying_symbols()
        self.assertNotIn(self.sym, result)

    def test_suppressed_future_excluded(self):
        """Symbol with suppress_until in the future should NOT appear."""
        self.sym.suppress_until = date.today() + timedelta(days=30)
        self.sym.save()
        result = get_qualifying_symbols()
        self.assertNotIn(self.sym, result)

    def test_suppressed_yesterday_included(self):
        """Symbol with suppress_until == yesterday should appear (strict inequality)."""
        self.sym.suppress_until = date.today() - timedelta(days=1)
        self.sym.save()
        result = get_qualifying_symbols()
        self.assertIn(self.sym, result)

    def test_null_suppress_until_included(self):
        """Symbol with no suppress_until should appear."""
        self.assertIsNone(self.sym.suppress_until)
        result = get_qualifying_symbols()
        self.assertIn(self.sym, result)
