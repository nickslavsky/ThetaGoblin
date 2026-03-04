# IV30 DoltHub Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace yfinance-based IV30 collection (biased to pre-screened candidates) with DoltHub API-based daily refresh covering the full symbol universe (~1,430 symbols/day).

**Architecture:** New `dolthub_client` service queries the public DoltHub SQL API. A `pull_iv` management command determines the date gap between local IV30Snapshot data and DoltHub, fetches missing days in alphabet-split batches (to stay under the 1,000-row API limit), and bulk-upserts into IV30Snapshot. IV30 logic is removed from `pull_options`. A new `run_iv_pipeline` orchestrates pull_iv → compute_iv_rank, scheduled daily at 8 PM ET.

**Tech Stack:** Python stdlib (`urllib.request`, `json`), Django ORM `bulk_create(update_conflicts=True)`, DoltHub public API, APScheduler

---

## Design Decisions

### Q1: Job tracking — dedicated table vs. derive from data?

**Recommendation: Derive from data.** Each table already has a natural watermark:
- IV30Snapshot: `MAX(date)` → last IV data we have
- Symbol: `fundamentals_updated_at` → staleness per symbol
- EarningsDate: `MAX(last_updated)` → last earnings pull
- OptionsSnapshot: `MAX(snapshot_date)` → last options pull

A `JobRun` audit table (started_at, finished_at, status, records_processed) would add operational visibility but isn't needed for correctness. It's a good future enhancement, not MVP-critical.

For `pull_iv` specifically: query `MAX(date)` from IV30Snapshot, then fetch every date after that from DoltHub. If the table is empty, default to 7 days back and log a warning to use `import_iv` for historical backfill.

### Q2: Working around the 1,000-row API limit

**Recommendation: Alphabet-split queries.** Tested empirically against 2026-03-03 data:

| Range | Count |
|-------|-------|
| A–F (`< 'G'`) | 532 |
| G–N (`>= 'G' AND < 'O'`) | 389 |
| O–Z (`>= 'O'`) | 509 |
| **Total** | **1,430** |

Three queries per date with comfortable headroom. The split boundaries are hardcoded in the client since the distribution is determined by the NYSE/NASDAQ ticker alphabet, which is very stable.

### Q3: Refresh frequency and DoltHub update cadence

**Recommendation: Daily at 8 PM ET (after market close).** DoltHub updates every trading day (verified: continuous data on weekdays, gaps on weekends). The command is idempotent — running on weekends is a no-op since no new DoltHub dates exist. Daily is cheap: typically 1 date × 3 queries + 1 MAX query = 4 HTTP calls.

---

## Task 1: Create DoltHub Client Service

**Files:**
- Create: `screener/services/dolthub_client.py`
- Test: `screener/tests/test_dolthub_client.py`

**Step 1: Write the failing test**

```python
# screener/tests/test_dolthub_client.py
from unittest.mock import patch, MagicMock
from django.test import TestCase

from screener.services.dolthub_client import fetch_iv_rows


class DoltHubClientTest(TestCase):

    @patch("screener.services.dolthub_client.urlopen")
    def test_parses_successful_response(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"query_execution_status":"Success","rows":[{"date":"2026-03-03","act_symbol":"AAPL","iv_current":"0.2828"}],"schema":[]}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        rows = fetch_iv_rows("2026-03-03", "2026-03-04", sym_min="A", sym_max=None)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["act_symbol"], "AAPL")
        self.assertEqual(rows[0]["iv_current"], "0.2828")

    @patch("screener.services.dolthub_client.urlopen")
    def test_returns_empty_on_api_error(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"query_execution_status":"Error","query_execution_message":"bad sql","rows":[],"schema":[]}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        rows = fetch_iv_rows("2026-03-03", "2026-03-04")
        self.assertEqual(rows, [])

    @patch("screener.services.dolthub_client.urlopen")
    def test_returns_empty_on_network_error(self, mock_urlopen):
        mock_urlopen.side_effect = OSError("connection refused")
        rows = fetch_iv_rows("2026-03-03", "2026-03-04")
        self.assertEqual(rows, [])
```

**Step 2: Run test to verify it fails**

Run: `docker compose exec web python manage.py test screener.tests.test_dolthub_client -v2`
Expected: ImportError — `dolthub_client` does not exist yet

**Step 3: Write minimal implementation**

```python
# screener/services/dolthub_client.py
"""Thin client for the DoltHub public SQL API (options/volatility_history)."""

import json
import logging
from urllib.parse import quote
from urllib.request import urlopen, Request

logger = logging.getLogger(__name__)

BASE_URL = "https://www.dolthub.com/api/v1alpha1/post-no-preference/options/master"
REQUEST_TIMEOUT = 30  # seconds


def fetch_iv_rows(date_from: str, date_to: str,
                  sym_min: str | None = None,
                  sym_max: str | None = None) -> list[dict]:
    """Fetch IV rows from DoltHub for a date range [date_from, date_to).

    Optional sym_min/sym_max filter on act_symbol for alphabet-split batching.
    Returns list of dicts with keys: date, act_symbol, iv_current.
    Returns [] on any error.
    """
    clauses = [
        f"date >= '{date_from}'",
        f"date < '{date_to}'",
        "iv_current IS NOT NULL",
    ]
    if sym_min:
        clauses.append(f"act_symbol >= '{sym_min}'")
    if sym_max:
        clauses.append(f"act_symbol < '{sym_max}'")

    sql = (
        "SELECT date, act_symbol, iv_current "
        "FROM `volatility_history` "
        f"WHERE {' AND '.join(clauses)} "
        "ORDER BY act_symbol"
    )

    url = f"{BASE_URL}?q={quote(sql)}"
    try:
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read())
    except Exception:
        logger.exception("DoltHub API request failed")
        return []

    if data.get("query_execution_status") != "Success":
        logger.error("DoltHub query error: %s", data.get("query_execution_message"))
        return []

    return data.get("rows", [])


def fetch_latest_date() -> str | None:
    """Return the most recent date available in DoltHub, or None on error."""
    sql = "SELECT MAX(date) as latest FROM `volatility_history` WHERE iv_current IS NOT NULL"
    url = f"{BASE_URL}?q={quote(sql)}"
    try:
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read())
    except Exception:
        logger.exception("DoltHub API request failed (latest date)")
        return None

    if data.get("query_execution_status") != "Success":
        return None

    rows = data.get("rows", [])
    if rows and rows[0].get("latest"):
        return rows[0]["latest"]
    return None
```

**Step 4: Run tests to verify they pass**

Run: `docker compose exec web python manage.py test screener.tests.test_dolthub_client -v2`
Expected: 3 tests PASS

**Step 5: Commit**

```bash
git add screener/services/dolthub_client.py screener/tests/test_dolthub_client.py
git commit -m "feat: add DoltHub API client for IV30 data"
```

---

## Task 2: Create `pull_iv` Management Command

**Files:**
- Create: `screener/management/commands/pull_iv.py`
- Test: `screener/tests/test_pull_iv.py`

**Step 1: Write the failing test**

```python
# screener/tests/test_pull_iv.py
from datetime import date, timedelta
from unittest.mock import patch
from django.test import TestCase
from django.core.management import call_command
from screener.models import Symbol, IV30Snapshot


class PullIVTest(TestCase):

    def setUp(self):
        self.aapl = Symbol.objects.create(
            ticker="AAPL", exchange_mic="XNAS", name="Apple Inc"
        )
        self.msft = Symbol.objects.create(
            ticker="MSFT", exchange_mic="XNAS", name="Microsoft"
        )

    @patch("screener.management.commands.pull_iv.dolthub_client.fetch_iv_rows")
    @patch("screener.management.commands.pull_iv.dolthub_client.fetch_latest_date")
    def test_fetches_and_upserts_iv_data(self, mock_latest, mock_rows):
        mock_latest.return_value = "2026-03-03"
        mock_rows.return_value = [
            {"date": "2026-03-03", "act_symbol": "AAPL", "iv_current": "0.2828"},
            {"date": "2026-03-03", "act_symbol": "MSFT", "iv_current": "0.3100"},
        ]
        call_command("pull_iv")
        self.assertEqual(IV30Snapshot.objects.count(), 2)
        snap = IV30Snapshot.objects.get(symbol=self.aapl)
        self.assertAlmostEqual(snap.iv30, 0.2828)

    @patch("screener.management.commands.pull_iv.dolthub_client.fetch_iv_rows")
    @patch("screener.management.commands.pull_iv.dolthub_client.fetch_latest_date")
    def test_skips_unknown_symbols(self, mock_latest, mock_rows):
        mock_latest.return_value = "2026-03-03"
        mock_rows.return_value = [
            {"date": "2026-03-03", "act_symbol": "AAPL", "iv_current": "0.28"},
            {"date": "2026-03-03", "act_symbol": "ZZZZ", "iv_current": "0.50"},
        ]
        call_command("pull_iv")
        self.assertEqual(IV30Snapshot.objects.count(), 1)

    @patch("screener.management.commands.pull_iv.dolthub_client.fetch_iv_rows")
    @patch("screener.management.commands.pull_iv.dolthub_client.fetch_latest_date")
    def test_incremental_from_existing_data(self, mock_latest, mock_rows):
        """Should only fetch dates after the latest local IV30Snapshot."""
        IV30Snapshot.objects.create(symbol=self.aapl, date=date(2026, 3, 2), iv30=0.25)
        mock_latest.return_value = "2026-03-03"
        mock_rows.return_value = [
            {"date": "2026-03-03", "act_symbol": "AAPL", "iv_current": "0.28"},
        ]
        call_command("pull_iv")
        # Should have old + new
        self.assertEqual(IV30Snapshot.objects.count(), 2)
        # Verify fetch was called with date_from = 2026-03-03 (day after existing)
        call_args = mock_rows.call_args_list[0]
        self.assertEqual(call_args[1].get("date_from", call_args[0][0]), "2026-03-03")

    @patch("screener.management.commands.pull_iv.dolthub_client.fetch_latest_date")
    def test_noop_when_already_current(self, mock_latest):
        """If local data matches DoltHub latest, nothing to fetch."""
        IV30Snapshot.objects.create(symbol=self.aapl, date=date(2026, 3, 3), iv30=0.25)
        mock_latest.return_value = "2026-03-03"
        call_command("pull_iv")
        self.assertEqual(IV30Snapshot.objects.count(), 1)  # unchanged

    @patch("screener.management.commands.pull_iv.dolthub_client.fetch_latest_date")
    def test_handles_dolthub_unavailable(self, mock_latest):
        mock_latest.return_value = None
        call_command("pull_iv")
        self.assertEqual(IV30Snapshot.objects.count(), 0)
```

**Step 2: Run tests to verify they fail**

Run: `docker compose exec web python manage.py test screener.tests.test_pull_iv -v2`
Expected: ImportError — `pull_iv` command does not exist yet

**Step 3: Write implementation**

```python
# screener/management/commands/pull_iv.py
import logging
import time
from datetime import date, datetime, timedelta

from django.core.management.base import BaseCommand

from screener.models import IV30Snapshot, Symbol
from screener.services import dolthub_client

logger = logging.getLogger(__name__)

BATCH_SIZE = 2000
# Alphabet splits to keep each query under DoltHub's 1000-row limit.
# Empirical counts (2026-03-03): A-F=532, G-N=389, O-Z=509. Total=1430.
ALPHA_SPLITS = [
    ("A", "G"),   # A–F
    ("G", "O"),   # G–N
    ("O", None),  # O–Z
]
REQUEST_DELAY = 1.0  # seconds between DoltHub API calls


class Command(BaseCommand):
    help = "Pull IV30 snapshots from DoltHub API and upsert into IV30Snapshot"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days-back", type=int, default=7,
            help="Fallback lookback if no existing IV30 data (default: 7)",
        )

    def handle(self, *args, **options):
        days_back = options["days_back"]

        # 1. Determine date range
        dolthub_latest = dolthub_client.fetch_latest_date()
        if dolthub_latest is None:
            self.stderr.write(self.style.ERROR("Could not reach DoltHub API. Aborting."))
            return

        local_latest = IV30Snapshot.objects.order_by("-date").values_list("date", flat=True).first()

        if local_latest is None:
            date_from = date.today() - timedelta(days=days_back)
            self.stdout.write(
                self.style.WARNING(
                    f"No existing IV30 data. Fetching from {date_from}. "
                    f"Use 'import_iv' for historical backfill."
                )
            )
        else:
            date_from = local_latest + timedelta(days=1)

        date_to = datetime.strptime(dolthub_latest, "%Y-%m-%d").date() + timedelta(days=1)

        if date_from >= date_to:
            self.stdout.write(f"Already up to date (latest: {local_latest}).")
            return

        self.stdout.write(
            f"Fetching IV30 from {date_from} to {dolthub_latest} "
            f"(DoltHub latest: {dolthub_latest})"
        )

        # 2. Pre-load symbol lookup
        symbol_map = dict(Symbol.objects.values_list("ticker", "id"))

        # 3. Fetch day-by-day in alphabet splits
        all_rows = []
        skipped_unknown = 0
        skipped_bad = 0
        current = date_from

        while current < date_to:
            day_str = current.isoformat()
            next_day_str = (current + timedelta(days=1)).isoformat()

            for sym_min, sym_max in ALPHA_SPLITS:
                rows = dolthub_client.fetch_iv_rows(
                    date_from=day_str, date_to=next_day_str,
                    sym_min=sym_min, sym_max=sym_max,
                )
                for row in rows:
                    ticker = row.get("act_symbol", "").strip()
                    iv_raw = row.get("iv_current", "").strip()

                    symbol_id = symbol_map.get(ticker)
                    if symbol_id is None:
                        skipped_unknown += 1
                        continue

                    if not iv_raw:
                        skipped_bad += 1
                        continue

                    try:
                        iv_val = float(iv_raw)
                    except (ValueError, TypeError):
                        skipped_bad += 1
                        continue

                    all_rows.append(
                        IV30Snapshot(symbol_id=symbol_id, date=current, iv30=iv_val)
                    )

                time.sleep(REQUEST_DELAY)

            logger.info("Fetched %s: %d rows so far", day_str, len(all_rows))
            current += timedelta(days=1)

        # 4. Bulk upsert
        upserted = 0
        for i in range(0, len(all_rows), BATCH_SIZE):
            batch = all_rows[i : i + BATCH_SIZE]
            IV30Snapshot.objects.bulk_create(
                batch,
                update_conflicts=True,
                unique_fields=["symbol", "date"],
                update_fields=["iv30"],
            )
            upserted += len(batch)

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Upserted: {upserted}, "
                f"Skipped unknown: {skipped_unknown}, "
                f"Skipped bad: {skipped_bad}"
            )
        )
```

**Step 4: Run tests to verify they pass**

Run: `docker compose exec web python manage.py test screener.tests.test_pull_iv -v2`
Expected: 5 tests PASS

**Step 5: Commit**

```bash
git add screener/management/commands/pull_iv.py screener/tests/test_pull_iv.py
git commit -m "feat: add pull_iv command to fetch IV30 from DoltHub API"
```

---

## Task 3: Remove IV30 Logic from pull_options.py

**Files:**
- Modify: `screener/management/commands/pull_options.py`
- Modify: `screener/tests/test_pull_options.py`

**Step 1: Update pull_options.py**

Remove these elements:
- Import of `IV30Snapshot` from models
- Import of `compute_atm_iv`, `select_iv30_from_expiries` from options_math
- The `expiry_ivs = []` initialization (line 57)
- The ATM IV computation block (lines 72-77)
- The IV30Snapshot upsert block (lines 121-127)

The command should now only concern itself with options chain snapshots.

After edits, the imports become:
```python
from screener.models import FilterConfig, OptionsSnapshot
from screener.services.options_math import compute_put_delta
```

And the per-symbol loop no longer collects `expiry_ivs` or writes IV30Snapshot.

**Step 2: Update test_pull_options.py**

Remove:
- `test_stores_iv30_snapshot` (test was validating IV30 from pull_options; now handled by pull_iv)
- `test_skips_iv30_when_none` (same reason)
- Import of `IV30Snapshot`

**Step 3: Run the remaining options tests**

Run: `docker compose exec web python manage.py test screener.tests.test_pull_options -v2`
Expected: 3 tests PASS (saves_snapshot, skips_outside_dte, handles_failure)

**Step 4: Run full test suite to check for regressions**

Run: `docker compose exec web python manage.py test -v2`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add screener/management/commands/pull_options.py screener/tests/test_pull_options.py
git commit -m "refactor: remove IV30 logic from pull_options (now in pull_iv)"
```

---

## Task 4: Create IV Pipeline and Update Scheduler

**Files:**
- Create: `screener/management/commands/run_iv_pipeline.py`
- Modify: `screener/management/commands/run_options_pipeline.py`
- Modify: `screener/scheduler.py`

**Step 1: Create run_iv_pipeline.py**

```python
# screener/management/commands/run_iv_pipeline.py
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run the IV pipeline: pull_iv from DoltHub then compute_iv_rank"

    def handle(self, *args, **options):
        self.stdout.write("=== Starting IV pipeline ===")
        call_command("pull_iv", stdout=self.stdout, stderr=self.stderr)
        call_command("compute_iv_rank", stdout=self.stdout, stderr=self.stderr)
        self.stdout.write("=== IV pipeline complete ===")
```

**Step 2: Remove compute_iv_rank from run_options_pipeline.py**

```python
# Updated run_options_pipeline.py
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run the options pipeline: pull_options for all qualifying symbols"

    def handle(self, *args, **options):
        self.stdout.write("=== Starting options pipeline ===")
        call_command("pull_options", stdout=self.stdout, stderr=self.stderr)
        self.stdout.write("=== Options pipeline complete ===")
```

**Step 3: Add daily IV pipeline job to scheduler.py**

```python
# Updated scheduler.py
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django.core.management import call_command

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def start():
    if scheduler.running:
        logger.debug("Scheduler already running, skipping start")
        return

    # Fundamentals + earnings: every Friday at 6 PM ET
    scheduler.add_job(
        lambda: call_command("run_fundamentals_pipeline"),
        trigger=CronTrigger(day_of_week="fri", hour=18, minute=0, timezone="America/New_York"),
        id="fundamentals_pipeline",
        replace_existing=True,
    )

    # Options chains: every Friday at 7 PM ET
    scheduler.add_job(
        lambda: call_command("run_options_pipeline"),
        trigger=CronTrigger(day_of_week="fri", hour=19, minute=0, timezone="America/New_York"),
        id="options_pipeline",
        replace_existing=True,
    )

    # IV refresh from DoltHub + rank computation: daily at 8 PM ET
    scheduler.add_job(
        lambda: call_command("run_iv_pipeline"),
        trigger=CronTrigger(hour=20, minute=0, timezone="America/New_York"),
        id="iv_pipeline",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        "APScheduler started: fundamentals Fri 18:00, options Fri 19:00, "
        "IV daily 20:00 ET"
    )
```

**Step 4: Run scheduler tests**

Run: `docker compose exec web python manage.py test screener.tests.test_scheduler -v2`
Expected: PASS (may need to update expected job count from 2 to 3)

**Step 5: Run full test suite**

Run: `docker compose exec web python manage.py test -v2`
Expected: All PASS

**Step 6: Commit**

```bash
git add screener/management/commands/run_iv_pipeline.py \
        screener/management/commands/run_options_pipeline.py \
        screener/scheduler.py
git commit -m "feat: add daily IV pipeline (DoltHub → IV rank), decouple from options pipeline"
```

---

## Task 5: End-to-End Smoke Test

**Step 1: Manual verification**

Run the new pipeline manually:
```bash
docker compose exec web python manage.py pull_iv --days-back=3
docker compose exec web python manage.py compute_iv_rank
```

Verify output shows upserted rows and no errors.

**Step 2: Verify data in Django admin**

Check IV30Snapshot admin: should show recent dates with data from DoltHub.
Check IVRank admin: ranks should be recomputed.

**Step 3: Verify candidates view still works**

Load the candidates page — should render with updated IV rank data.

**Step 4: Final commit if any fixups needed**

---

## Summary of Changes

| File | Action |
|------|--------|
| `screener/services/dolthub_client.py` | **Create** — DoltHub HTTP client |
| `screener/tests/test_dolthub_client.py` | **Create** — Client tests |
| `screener/management/commands/pull_iv.py` | **Create** — Incremental IV30 fetch |
| `screener/tests/test_pull_iv.py` | **Create** — Command tests |
| `screener/management/commands/pull_options.py` | **Modify** — Remove IV30 logic |
| `screener/tests/test_pull_options.py` | **Modify** — Remove IV30 tests |
| `screener/management/commands/run_iv_pipeline.py` | **Create** — Orchestrates pull_iv → compute_iv_rank |
| `screener/management/commands/run_options_pipeline.py` | **Modify** — Remove compute_iv_rank step |
| `screener/scheduler.py` | **Modify** — Add daily IV pipeline job |
