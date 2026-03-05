from datetime import date
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
            cash_flow_per_share_annual=7.5,
            long_term_debt_to_equity_annual=1.2,
            ten_day_avg_trading_volume=5_000_000,
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
