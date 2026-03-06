from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.core.management import call_command

from screener.models import Symbol, IV30Snapshot, IVRank


TODAY = date(2026, 3, 6)


class ComputeIVRankCommandTest(TestCase):

    def setUp(self):
        self.sym = Symbol.objects.create(
            ticker="AAPL", exchange_mic="XNAS", name="Apple Inc"
        )

    @patch("screener.management.commands.compute_iv_rank.date")
    def _call(self, mock_date):
        mock_date.today.return_value = TODAY
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        call_command("compute_iv_rank")

    def test_single_data_point_no_rank(self):
        """With only 1 IV30 snapshot (max==min), no IVRank created."""
        IV30Snapshot.objects.create(symbol=self.sym, date=TODAY - timedelta(days=1), iv30=0.28)
        self._call()
        self.assertEqual(IVRank.objects.count(), 0)

    def test_two_data_points_creates_rank(self):
        """With 2 IV30 snapshots within window, IVRank created, is_reliable=False."""
        IV30Snapshot.objects.create(symbol=self.sym, date=TODAY - timedelta(days=7), iv30=0.20)
        IV30Snapshot.objects.create(symbol=self.sym, date=TODAY, iv30=0.30)
        self._call()
        self.assertEqual(IVRank.objects.count(), 1)
        rank = IVRank.objects.first()
        self.assertAlmostEqual(rank.iv_rank, 100.0)
        self.assertFalse(rank.is_reliable)

    def test_skips_symbols_without_iv30(self):
        """Symbols with no IV30 history should be skipped."""
        Symbol.objects.create(ticker="MSFT", exchange_mic="XNAS", name="Microsoft")
        self._call()
        self.assertEqual(IVRank.objects.count(), 0)

    def test_reliable_based_on_date_span(self):
        """IV30 data spanning 365+ days marks is_reliable=True."""
        IV30Snapshot.objects.create(
            symbol=self.sym, date=TODAY - timedelta(days=365), iv30=0.20
        )
        IV30Snapshot.objects.create(
            symbol=self.sym, date=TODAY, iv30=0.30
        )
        self._call()
        rank = IVRank.objects.get(symbol=self.sym)
        self.assertTrue(rank.is_reliable)

    def test_not_reliable_short_span(self):
        """IV30 data spanning < 364 days marks is_reliable=False."""
        IV30Snapshot.objects.create(
            symbol=self.sym, date=TODAY - timedelta(days=100), iv30=0.20
        )
        IV30Snapshot.objects.create(
            symbol=self.sym, date=TODAY, iv30=0.30
        )
        self._call()
        rank = IVRank.objects.get(symbol=self.sym)
        self.assertFalse(rank.is_reliable)

    def test_data_outside_window_excluded(self):
        """IV30 snapshots older than 365 days don't affect rank computation."""
        # Old point outside window would lower min to 0.05
        IV30Snapshot.objects.create(
            symbol=self.sym, date=TODAY - timedelta(days=400), iv30=0.05
        )
        # Three points inside window, current (0.30) is in the middle
        IV30Snapshot.objects.create(
            symbol=self.sym, date=TODAY - timedelta(days=10), iv30=0.20
        )
        IV30Snapshot.objects.create(
            symbol=self.sym, date=TODAY - timedelta(days=5), iv30=0.40
        )
        IV30Snapshot.objects.create(
            symbol=self.sym, date=TODAY, iv30=0.30
        )
        self._call()
        rank = IVRank.objects.get(symbol=self.sym)
        # Window: [0.20, 0.40, 0.30]. min=0.20, max=0.40, current=0.30
        # iv_rank = (0.30-0.20)/(0.40-0.20)*100 = 50
        # If 0.05 were included: (0.30-0.05)/(0.40-0.05)*100 = 71.4
        self.assertAlmostEqual(rank.iv_rank, 50.0)

    def test_stale_ivrank_cleaned_up(self):
        """IVRank rows from a previous run are deleted if symbol has no data in window."""
        # Create an old IVRank that won't be refreshed
        other = Symbol.objects.create(ticker="GOOG", exchange_mic="XNAS", name="Google")
        IVRank.objects.create(
            symbol=other,
            computed_date=TODAY - timedelta(days=1),
            iv_rank=50.0,
            iv_percentile=50.0,
            weeks_of_history=10,
            is_reliable=False,
        )
        # AAPL has data in window so will get a fresh IVRank
        IV30Snapshot.objects.create(
            symbol=self.sym, date=TODAY - timedelta(days=7), iv30=0.20
        )
        IV30Snapshot.objects.create(symbol=self.sym, date=TODAY, iv30=0.30)
        self._call()
        # GOOG stale row should be cleaned up
        self.assertFalse(IVRank.objects.filter(symbol=other).exists())
        # AAPL should still have its fresh rank
        self.assertTrue(IVRank.objects.filter(symbol=self.sym).exists())

    def test_weeks_of_history_reflects_date_span(self):
        """weeks_of_history = (latest - earliest).days // 7."""
        # 49 days apart = 7 weeks
        IV30Snapshot.objects.create(
            symbol=self.sym, date=TODAY - timedelta(days=49), iv30=0.20
        )
        IV30Snapshot.objects.create(symbol=self.sym, date=TODAY, iv30=0.30)
        self._call()
        rank = IVRank.objects.get(symbol=self.sym)
        self.assertEqual(rank.weeks_of_history, 7)
