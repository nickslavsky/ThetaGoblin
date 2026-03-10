from datetime import date
from unittest.mock import patch

from django.test import TestCase

from screener.models import IV30Snapshot, Symbol


class PullIVYfinanceTest(TestCase):

    def setUp(self):
        self.sym1 = Symbol.objects.create(
            ticker="AAPL", exchange_mic="XNAS", name="Apple Inc",
        )
        self.sym2 = Symbol.objects.create(
            ticker="MSFT", exchange_mic="XNAS", name="Microsoft Corp",
        )

    @patch("screener.management.commands.pull_iv_yfinance.call_with_backoff")
    def test_creates_snapshots_for_successful_symbols(self, mock_backoff):
        mock_backoff.side_effect = [0.28, 0.32]

        from django.core.management import call_command
        call_command("pull_iv_yfinance")

        snapshots = IV30Snapshot.objects.all()
        self.assertEqual(snapshots.count(), 2)

        aapl_snap = IV30Snapshot.objects.get(symbol=self.sym1)
        self.assertAlmostEqual(aapl_snap.iv30_yfinance, 0.28)
        self.assertEqual(aapl_snap.date, date.today())
        self.assertIsNone(aapl_snap.iv30)  # DoltHub didn't write this

    @patch("screener.management.commands.pull_iv_yfinance.call_with_backoff")
    def test_skips_failed_symbols(self, mock_backoff):
        """Symbols that return None from backoff (exhausted retries) are skipped."""
        mock_backoff.side_effect = [0.28, None]

        from django.core.management import call_command
        call_command("pull_iv_yfinance")

        self.assertEqual(IV30Snapshot.objects.count(), 1)
        self.assertTrue(IV30Snapshot.objects.filter(symbol=self.sym1).exists())
        self.assertFalse(IV30Snapshot.objects.filter(symbol=self.sym2).exists())

    @patch("screener.management.commands.pull_iv_yfinance.call_with_backoff")
    def test_skips_symbols_already_computed_today(self, mock_backoff):
        """Symbols with non-null iv30_yfinance for today should be skipped entirely."""
        IV30Snapshot.objects.create(
            symbol=self.sym1, date=date.today(), iv30=0.25, iv30_yfinance=0.30,
        )
        mock_backoff.return_value = 0.35

        from django.core.management import call_command
        call_command("pull_iv_yfinance")

        # AAPL skipped (already done), only MSFT fetched
        mock_backoff.assert_called_once()
        snap_aapl = IV30Snapshot.objects.get(symbol=self.sym1, date=date.today())
        self.assertAlmostEqual(snap_aapl.iv30_yfinance, 0.30)  # unchanged
        snap_msft = IV30Snapshot.objects.get(symbol=self.sym2, date=date.today())
        self.assertAlmostEqual(snap_msft.iv30_yfinance, 0.35)

    @patch("screener.management.commands.pull_iv_yfinance.call_with_backoff")
    def test_does_not_skip_dolthub_only_snapshot(self, mock_backoff):
        """Snapshot with iv30 but null iv30_yfinance should still be processed."""
        IV30Snapshot.objects.create(
            symbol=self.sym1, date=date.today(), iv30=0.25, iv30_yfinance=None,
        )
        mock_backoff.side_effect = [0.30, 0.35]

        from django.core.management import call_command
        call_command("pull_iv_yfinance")

        # Both symbols processed — AAPL had DoltHub data but no yfinance yet
        self.assertEqual(mock_backoff.call_count, 2)
        snap = IV30Snapshot.objects.get(symbol=self.sym1, date=date.today())
        self.assertAlmostEqual(snap.iv30, 0.25)  # DoltHub preserved
        self.assertAlmostEqual(snap.iv30_yfinance, 0.30)  # yfinance filled in

    @patch("screener.management.commands.pull_iv_yfinance.call_with_backoff")
    def test_limit_flag_restricts_symbols(self, mock_backoff):
        mock_backoff.return_value = 0.28

        from django.core.management import call_command
        call_command("pull_iv_yfinance", limit=1)

        self.assertEqual(IV30Snapshot.objects.count(), 1)
