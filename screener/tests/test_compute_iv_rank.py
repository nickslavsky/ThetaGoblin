from datetime import date, timedelta
from django.test import TestCase
from django.core.management import call_command
from screener.models import Symbol, IV30Snapshot, IVRank


class ComputeIVRankCommandTest(TestCase):

    def setUp(self):
        self.sym = Symbol.objects.create(
            ticker="AAPL", exchange_mic="XNAS", name="Apple Inc"
        )

    def test_single_data_point_no_rank(self):
        """With only 1 IV30 snapshot, compute_iv_rank should not create an IVRank."""
        IV30Snapshot.objects.create(symbol=self.sym, date=date(2026, 2, 1), iv30=0.28)
        call_command("compute_iv_rank")
        self.assertEqual(IVRank.objects.count(), 0)

    def test_two_data_points_creates_rank(self):
        """With 2 IV30 snapshots, IVRank should be created with is_reliable=False."""
        IV30Snapshot.objects.create(symbol=self.sym, date=date(2026, 2, 1), iv30=0.20)
        IV30Snapshot.objects.create(symbol=self.sym, date=date(2026, 2, 8), iv30=0.30)
        call_command("compute_iv_rank")
        self.assertEqual(IVRank.objects.count(), 1)
        rank = IVRank.objects.first()
        self.assertAlmostEqual(rank.iv_rank, 100.0)  # current (0.30) is max
        self.assertFalse(rank.is_reliable)

    def test_skips_symbols_without_iv30(self):
        """Symbols with no IV30 history should be skipped."""
        Symbol.objects.create(ticker="MSFT", exchange_mic="XNAS", name="Microsoft")
        call_command("compute_iv_rank")
        self.assertEqual(IVRank.objects.count(), 0)
