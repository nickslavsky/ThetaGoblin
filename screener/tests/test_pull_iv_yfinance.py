from datetime import date
from unittest.mock import patch

from django.test import TestCase

from screener.models import IV30Snapshot, Symbol
from screener.services.yfinance_svc import NoOptionsError

MARKET_OPEN = "screener.management.commands.pull_iv_yfinance._market_was_open_today"


@patch(MARKET_OPEN, return_value=True)
class PullIVYfinanceTest(TestCase):

    def setUp(self):
        self.sym1 = Symbol.objects.create(
            ticker="AAPL", exchange_mic="XNAS", name="Apple Inc",
        )
        self.sym2 = Symbol.objects.create(
            ticker="MSFT", exchange_mic="XNAS", name="Microsoft Corp",
        )

    @patch("screener.management.commands.pull_iv_yfinance.call_with_backoff")
    def test_creates_snapshots_for_successful_symbols(self, mock_backoff, _):
        mock_backoff.side_effect = [0.28, 0.32]

        from django.core.management import call_command
        call_command("pull_iv_yfinance")

        snapshots = IV30Snapshot.objects.all()
        self.assertEqual(snapshots.count(), 2)

        aapl_snap = IV30Snapshot.objects.get(symbol=self.sym1)
        self.assertAlmostEqual(aapl_snap.iv30, 0.28)
        self.assertEqual(aapl_snap.date, date.today())

    @patch("screener.management.commands.pull_iv_yfinance.call_with_backoff")
    def test_skips_failed_symbols(self, mock_backoff, _):
        """Symbols that return None from backoff (exhausted retries) are skipped."""
        mock_backoff.side_effect = [0.28, None]

        from django.core.management import call_command
        call_command("pull_iv_yfinance")

        self.assertEqual(IV30Snapshot.objects.count(), 1)
        self.assertTrue(IV30Snapshot.objects.filter(symbol=self.sym1).exists())
        self.assertFalse(IV30Snapshot.objects.filter(symbol=self.sym2).exists())

    @patch("screener.management.commands.pull_iv_yfinance.call_with_backoff")
    def test_skips_symbols_already_computed_today(self, mock_backoff, _):
        """Symbols with a snapshot for today should be skipped entirely."""
        IV30Snapshot.objects.create(
            symbol=self.sym1, date=date.today(), iv30=0.30,
        )
        mock_backoff.return_value = 0.35

        from django.core.management import call_command
        call_command("pull_iv_yfinance")

        # AAPL skipped (already done), only MSFT fetched
        mock_backoff.assert_called_once()
        snap_aapl = IV30Snapshot.objects.get(symbol=self.sym1, date=date.today())
        self.assertAlmostEqual(snap_aapl.iv30, 0.30)  # unchanged
        snap_msft = IV30Snapshot.objects.get(symbol=self.sym2, date=date.today())
        self.assertAlmostEqual(snap_msft.iv30, 0.35)

    @patch("screener.management.commands.pull_iv_yfinance.call_with_backoff")
    def test_no_options_skipped_without_retry(self, mock_backoff, _):
        """Symbols with no options should be skipped immediately, not retried."""
        mock_backoff.side_effect = [NoOptionsError("No options"), 0.35]

        from django.core.management import call_command
        call_command("pull_iv_yfinance")

        # Only MSFT gets a snapshot — AAPL had no options
        self.assertEqual(IV30Snapshot.objects.count(), 1)
        self.assertFalse(IV30Snapshot.objects.filter(symbol=self.sym1).exists())
        self.assertTrue(IV30Snapshot.objects.filter(symbol=self.sym2).exists())

    @patch("screener.management.commands.pull_iv_yfinance.call_with_backoff")
    def test_limit_flag_restricts_symbols(self, mock_backoff, _):
        mock_backoff.return_value = 0.28

        from django.core.management import call_command
        call_command("pull_iv_yfinance", limit=1)

        self.assertEqual(IV30Snapshot.objects.count(), 1)


class MarketClosedGuardTest(TestCase):

    @patch(MARKET_OPEN, return_value=False)
    @patch("screener.management.commands.pull_iv_yfinance.call_with_backoff")
    def test_skips_when_market_closed(self, mock_backoff, _):
        """No symbols should be fetched when the market was closed."""
        Symbol.objects.create(ticker="AAPL", exchange_mic="XNAS", name="Apple Inc")

        from django.core.management import call_command
        call_command("pull_iv_yfinance")

        mock_backoff.assert_not_called()
        self.assertEqual(IV30Snapshot.objects.count(), 0)
