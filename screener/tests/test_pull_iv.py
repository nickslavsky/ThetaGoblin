from datetime import date, timedelta
from unittest.mock import patch, call

from django.test import TestCase, override_settings
from django.core.management import call_command

from screener.models import Symbol, IV30Snapshot


SAMPLE_ROWS = [
    {"date": "2026-03-03", "act_symbol": "AAPL", "iv_current": "0.2828"},
    {"date": "2026-03-03", "act_symbol": "MSFT", "iv_current": "0.1950"},
]


@override_settings(DOLTHUB_REQUEST_DELAY=0)
class PullIvTest(TestCase):

    def setUp(self):
        self.aapl = Symbol.objects.create(
            ticker="AAPL", exchange_mic="XNAS", name="Apple Inc"
        )
        self.msft = Symbol.objects.create(
            ticker="MSFT", exchange_mic="XNAS", name="Microsoft Corp"
        )

    @patch("screener.management.commands.pull_iv.time.sleep")
    @patch("screener.services.dolthub_client.fetch_iv_rows")
    @patch("screener.services.dolthub_client.fetch_latest_date")
    def test_fetches_and_upserts_iv_data(self, mock_latest, mock_fetch, mock_sleep):
        """Fetches data for 2 known symbols and creates IV30Snapshot rows."""
        mock_latest.return_value = "2026-03-03"
        # Seed existing data so only one day (2026-03-03) is fetched
        IV30Snapshot.objects.create(
            symbol=self.aapl, date=date(2026, 3, 2), iv30=0.20
        )
        # Return same data for all 3 alphabet-split calls (deduped by command)
        mock_fetch.return_value = SAMPLE_ROWS

        call_command("pull_iv")

        # 2 symbols x 1 day = 2 new rows (plus the 1 pre-existing)
        self.assertEqual(IV30Snapshot.objects.count(), 3)
        aapl_snap = IV30Snapshot.objects.get(symbol=self.aapl, date=date(2026, 3, 3))
        self.assertAlmostEqual(aapl_snap.iv30, 0.2828)
        msft_snap = IV30Snapshot.objects.get(symbol=self.msft, date=date(2026, 3, 3))
        self.assertAlmostEqual(msft_snap.iv30, 0.1950)
        # 1 day x 3 splits = 3 fetch_iv_rows calls
        self.assertEqual(mock_fetch.call_count, 3)

    @patch("screener.management.commands.pull_iv.time.sleep")
    @patch("screener.services.dolthub_client.fetch_iv_rows")
    @patch("screener.services.dolthub_client.fetch_latest_date")
    def test_skips_unknown_symbols(self, mock_latest, mock_fetch, mock_sleep):
        """Ticker not in Symbol table is skipped without error."""
        mock_latest.return_value = "2026-03-03"
        # Seed existing data so only one day is fetched
        IV30Snapshot.objects.create(
            symbol=self.aapl, date=date(2026, 3, 2), iv30=0.20
        )
        rows_with_unknown = SAMPLE_ROWS + [
            {"date": "2026-03-03", "act_symbol": "ZZZZ", "iv_current": "0.50"},
        ]
        mock_fetch.return_value = rows_with_unknown

        call_command("pull_iv")

        # Only AAPL and MSFT should be stored for 2026-03-03, not ZZZZ
        # Plus the 1 pre-existing row = 3 total
        self.assertEqual(
            IV30Snapshot.objects.filter(date=date(2026, 3, 3)).count(), 2
        )
        self.assertFalse(
            IV30Snapshot.objects.filter(symbol__ticker="ZZZZ").exists()
        )

    @patch("screener.management.commands.pull_iv.time.sleep")
    @patch("screener.services.dolthub_client.fetch_iv_rows")
    @patch("screener.services.dolthub_client.fetch_latest_date")
    def test_incremental_from_existing_data(self, mock_latest, mock_fetch, mock_sleep):
        """When existing IV30 data exists, only fetch newer dates."""
        # Pre-existing snapshot for 2026-03-02
        IV30Snapshot.objects.create(
            symbol=self.aapl, date=date(2026, 3, 2), iv30=0.25
        )
        mock_latest.return_value = "2026-03-04"
        mock_fetch.return_value = [
            {"date": "2026-03-03", "act_symbol": "AAPL", "iv_current": "0.28"},
        ]

        call_command("pull_iv")

        # fetch_iv_rows should only be called for dates 2026-03-03 and 2026-03-04
        # That's 2 dates x 3 alphabet splits = 6 calls
        self.assertEqual(mock_fetch.call_count, 6)

        # Verify the date_from values for each day's calls
        # Day 1 (calls 0-2): date_from="2026-03-03"
        # Day 2 (calls 3-5): date_from="2026-03-04"
        for c in mock_fetch.call_args_list[:3]:
            self.assertEqual(c[1]["date_from"], "2026-03-03")
        for c in mock_fetch.call_args_list[3:]:
            self.assertEqual(c[1]["date_from"], "2026-03-04")

    @patch("screener.management.commands.pull_iv.time.sleep")
    @patch("screener.services.dolthub_client.fetch_iv_rows")
    @patch("screener.services.dolthub_client.fetch_latest_date")
    def test_noop_when_already_current(self, mock_latest, mock_fetch, mock_sleep):
        """When local latest >= dolthub latest, no fetch calls are made."""
        IV30Snapshot.objects.create(
            symbol=self.aapl, date=date(2026, 3, 3), iv30=0.28
        )
        mock_latest.return_value = "2026-03-03"

        call_command("pull_iv")

        mock_fetch.assert_not_called()

    @patch("screener.management.commands.pull_iv.time.sleep")
    @patch("screener.services.dolthub_client.fetch_iv_rows")
    @patch("screener.services.dolthub_client.fetch_latest_date")
    def test_handles_dolthub_unavailable(self, mock_latest, mock_fetch, mock_sleep):
        """When fetch_latest_date returns None, exit gracefully."""
        mock_latest.return_value = None

        call_command("pull_iv")

        mock_fetch.assert_not_called()
