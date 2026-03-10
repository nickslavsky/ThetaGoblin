# Yahoo Fundamentals Refactor — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Finnhub fundamentals with yfinance `.info` data, rename model fields to match actual semantics, and wire up the fundamentals pipeline to use yfinance with exponential backoff.

**Architecture:** The yfinance `.info` call returns all needed fundamentals in a single request per symbol — no separate calls needed. We rename 3 model columns to match the new data semantics (`free_cash_flow`, `debt_to_equity`, `avg_volume_10d`), add a `fetch_fundamentals()` function to `yfinance_svc.py` with a typed exception for backoff, and rewire `pull_fundamentals` to use it. Volume units change from millions (Finnhub) to raw shares (Yahoo) — existing data and the FilterConfig threshold are converted in the migration.

**Tech Stack:** Django 5.x, yfinance, PostgreSQL 17

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `screener/models.py` | Modify | Rename 3 fields |
| `screener/migrations/0012_rename_fundamental_fields.py` | Create | Column renames + data conversion + FilterConfig update |
| `screener/services/yfinance_svc.py` | Modify | Add `YFinanceError`, `fetch_fundamentals()` |
| `thetagoblin/settings.py` | Modify | Add `YFINANCE_REQUEST_DELAY` |
| `screener/management/commands/pull_fundamentals.py` | Modify | Swap finnhub for yfinance |
| `screener/services/candidates.py` | Modify | Update field names in ORM filter |
| `screener/admin.py` | Modify | Update `list_display` field names |
| `screener/management/commands/load_symbols.py` | Modify | Update `defaults` dict field names |
| `screener/services/finnhub_client.py` | Modify | Remove `fetch_fundamentals()` (keep `fetch_earnings`, `fetch_symbols`) |
| `screener/tests/test_yfinance_svc.py` | Modify | Add tests for `fetch_fundamentals` (file already has tests for options functions) |
| `screener/tests/test_pull_fundamentals.py` | Modify | Swap mocks from finnhub to yfinance |
| `screener/tests/test_finnhub_client.py` | Modify | Remove fundamentals test |
| `screener/tests/test_candidates.py` | Modify | Update fixture field names |
| `screener/tests/test_views.py` | Modify | Update fixture field names |
| `screener/tests/test_live_options.py` | Modify | Update fixture field names |
| `screener/tests/test_load_symbols.py` | Modify | Update CSV field names |

## Important context

### Volume unit change

Finnhub stored `ten_day_avg_trading_volume` in **millions** (e.g. NVDA = 194.19). Yahoo's `averageVolume10days` returns **raw shares** (e.g. 43,457,250). The migration must:
1. Multiply existing column values by 1,000,000
2. Update FilterConfig `min_avg_volume` from `1.5` to `1500000`
3. Update its description to say "shares" not "millions of shares"

### yfinance `.info` field mapping

| Model field (new) | yfinance key | Notes |
|---|---|---|
| `market_cap` | `marketCap` | int, USD |
| `operating_margin` | `operatingMargins` | float, decimal (0.35 = 35%) |
| `free_cash_flow` | `freeCashflow` | int, absolute USD |
| `debt_to_equity` | `debtToEquity` | float, percentage (102.63 = 1.03x). Note: Yahoo reports as percentage, so 102.63 means D/E of 1.03. Store as-is (the FilterConfig `debt_to_equity_max` of 2.0 was set for a ratio, so it needs to become 200.0 in the migration) |
| `avg_volume_10d` | `averageVolume10days` | int, raw shares |

### debt_to_equity unit clarification

Finnhub's `longTermDebt/equityAnnual` returns a ratio (e.g. 1.2 = 120% D/E). Yahoo's `debtToEquity` returns a percentage (e.g. 102.63 means total debt is 102.63% of equity, i.e. ratio of 1.0263). Current FilterConfig `debt_to_equity_max` is `2.0` (Finnhub ratio scale). Must convert to `200.0` (Yahoo percentage scale) in migration.

### Test command

```bash
docker compose exec web python manage.py test screener --verbosity=2
```

---

## Chunk 1: Model, Migration, and Service Layer

### Task 1: Add `YFINANCE_REQUEST_DELAY` to Django settings

**Files:**
- Modify: `thetagoblin/settings.py:81` (near `FINNHUB_REQUEST_DELAY`)

- [ ] **Step 1: Add the setting**

In `thetagoblin/settings.py`, after the `FINNHUB_REQUEST_DELAY` line, add:

```python
YFINANCE_REQUEST_DELAY = float(os.environ.get("YFINANCE_REQUEST_DELAY", "0.5"))
```

- [ ] **Step 2: Commit**

```bash
git add thetagoblin/settings.py
git commit -m "feat: add YFINANCE_REQUEST_DELAY setting"
```

---

### Task 2: Add `YFinanceError` and `fetch_fundamentals()` to yfinance_svc

**Files:**
- Modify: `screener/services/yfinance_svc.py`
- Modify: `screener/tests/test_yfinance_svc.py` (file exists with options tests — append new class)

- [ ] **Step 1: Write the failing tests**

Add the following test class to the **end** of the existing `screener/tests/test_yfinance_svc.py` (do NOT replace existing tests):

```python
from unittest.mock import patch, MagicMock
from django.test import TestCase
from screener.services.yfinance_svc import fetch_fundamentals, YFinanceError


class FetchFundamentalsTest(TestCase):

    @patch("screener.services.yfinance_svc.yf.Ticker")
    def test_returns_correct_fields(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "marketCap": 3_835_868_741_632,
            "operatingMargins": 0.35374,
            "freeCashflow": 106_312_753_152,
            "debtToEquity": 102.63,
            "averageVolume10days": 43_457_250,
        }
        mock_ticker_cls.return_value = mock_ticker

        result = fetch_fundamentals("AAPL")

        self.assertEqual(result["market_cap"], 3_835_868_741_632)
        self.assertAlmostEqual(result["operating_margin"], 0.35374)
        self.assertEqual(result["free_cash_flow"], 106_312_753_152)
        self.assertAlmostEqual(result["debt_to_equity"], 102.63)
        self.assertEqual(result["avg_volume_10d"], 43_457_250)

    @patch("screener.services.yfinance_svc.yf.Ticker")
    def test_handles_missing_fields_gracefully(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.info = {"marketCap": 1_000_000_000}
        mock_ticker_cls.return_value = mock_ticker

        result = fetch_fundamentals("XYZ")

        self.assertEqual(result["market_cap"], 1_000_000_000)
        self.assertIsNone(result["operating_margin"])
        self.assertIsNone(result["free_cash_flow"])
        self.assertIsNone(result["debt_to_equity"])
        self.assertIsNone(result["avg_volume_10d"])

    @patch("screener.services.yfinance_svc.yf.Ticker")
    def test_raises_yfinance_error_on_exception(self, mock_ticker_cls):
        mock_ticker_cls.side_effect = Exception("network timeout")

        with self.assertRaises(YFinanceError):
            fetch_fundamentals("AAPL")

    @patch("screener.services.yfinance_svc.yf.Ticker")
    def test_raises_yfinance_error_on_empty_info(self, mock_ticker_cls):
        """yfinance returns empty dict when ticker is delisted/invalid."""
        mock_ticker = MagicMock()
        mock_ticker.info = {}
        mock_ticker_cls.return_value = mock_ticker

        with self.assertRaises(YFinanceError):
            fetch_fundamentals("INVALID")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose exec web python manage.py test screener.tests.test_yfinance_svc -v2
```

Expected: FAIL — `YFinanceError` and `fetch_fundamentals` don't exist yet.

- [ ] **Step 3: Implement `YFinanceError` and `fetch_fundamentals`**

In `screener/services/yfinance_svc.py`, add the exception class near the top (after `logger`) and the function at the bottom:

```python
class YFinanceError(Exception):
    """Raised on yfinance errors that should trigger backoff retry."""
    pass
```

```python
def _safe_optional(val):
    """Return val as-is if it's a real number, else None."""
    if val is None:
        return None
    try:
        f = float(val)
        return None if math.isnan(f) else val
    except (TypeError, ValueError):
        return None


def fetch_fundamentals(ticker: str) -> dict:
    """Fetch fundamental metrics for a single ticker from yfinance.

    Returns a dict with keys matching Symbol model fields.
    Raises YFinanceError on any failure (for backoff compatibility).
    """
    try:
        t = yf.Ticker(ticker)
        info = t.info
    except Exception as exc:
        raise YFinanceError(f"Failed to fetch info for {ticker}: {exc}") from exc

    if not info:
        raise YFinanceError(f"Empty info response for {ticker}")

    return {
        "market_cap": _safe_int(info.get("marketCap"), default=None),
        "operating_margin": _safe_optional(info.get("operatingMargins")),
        "free_cash_flow": _safe_int(info.get("freeCashflow"), default=None),
        "debt_to_equity": _safe_optional(info.get("debtToEquity")),
        "avg_volume_10d": _safe_int(info.get("averageVolume10days"), default=None),
    }
```

**Important:** Before adding `fetch_fundamentals`, first update `_safe_int` to support `None` default (needed for `fetch_fundamentals` to return `None` instead of `0` for missing fields). Change the existing signature from:

```python
def _safe_int(val, default: int = 0) -> int:
```

to:

```python
def _safe_int(val, default: int | None = 0) -> int | None:
```

This is backwards-compatible — existing callers that don't pass `default` still get `0`.

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker compose exec web python manage.py test screener.tests.test_yfinance_svc -v2
```

Expected: all 4 pass.

- [ ] **Step 5: Commit**

```bash
git add screener/services/yfinance_svc.py screener/tests/test_yfinance_svc.py
git commit -m "feat: add fetch_fundamentals to yfinance_svc with YFinanceError"
```

---

### Task 3: Rename model fields and create migration

**Files:**
- Modify: `screener/models.py:9-12`
- Create: `screener/migrations/0012_rename_fundamental_fields.py`

- [ ] **Step 1: Update the model**

In `screener/models.py`, change:

```python
    # OLD
    cash_flow_per_share_annual = models.FloatField(null=True, blank=True)
    long_term_debt_to_equity_annual = models.FloatField(null=True, blank=True)
    ten_day_avg_trading_volume = models.FloatField(null=True, blank=True)

    # NEW
    free_cash_flow = models.FloatField(null=True, blank=True)
    debt_to_equity = models.FloatField(null=True, blank=True)
    avg_volume_10d = models.FloatField(null=True, blank=True)
```

- [ ] **Step 2: Generate the migration**

```bash
docker compose exec web python manage.py makemigrations screener --name rename_fundamental_fields
```

Django should detect the renames and ask if each field was renamed (answer yes to all 3). Verify the generated migration contains `RenameField` operations (not remove+add).

- [ ] **Step 3: Add data migration for volume conversion and FilterConfig updates**

Edit the generated migration to add a `RunPython` operation **after** the renames. Add this function and operation:

```python
def convert_volume_and_update_configs(apps, schema_editor):
    """Convert volume from millions to raw shares, update FilterConfig units."""
    Symbol = apps.get_model("screener", "Symbol")
    FilterConfig = apps.get_model("screener", "FilterConfig")

    # Convert existing volume data from millions to raw shares
    from django.db.models import F
    Symbol.objects.filter(avg_volume_10d__isnull=False).update(
        avg_volume_10d=F("avg_volume_10d") * 1_000_000
    )

    # Update min_avg_volume threshold: 1.5 (millions) -> 1500000 (raw shares)
    FilterConfig.objects.filter(key="min_avg_volume").update(
        value="1500000",
        description="Minimum 10-day average trading volume (shares)",
    )

    # Update debt_to_equity_max: 2.0 (ratio) -> 200.0 (percentage, Yahoo scale)
    FilterConfig.objects.filter(key="debt_to_equity_max").update(
        value="200.0",
        description="Maximum total debt/equity (Yahoo percentage scale, 200 = 2x)",
    )

    # Update free_cash_flow_min description
    FilterConfig.objects.filter(key="free_cash_flow_min").update(
        description="Minimum free cash flow (absolute USD, 0 = positive FCF)",
    )


def reverse_convert(apps, schema_editor):
    Symbol = apps.get_model("screener", "Symbol")
    FilterConfig = apps.get_model("screener", "FilterConfig")

    Symbol.objects.filter(avg_volume_10d__isnull=False).update(
        avg_volume_10d=F("avg_volume_10d") / 1_000_000
    )
    FilterConfig.objects.filter(key="min_avg_volume").update(
        value="1.5",
        description="Minimum 10-day average trading volume (millions of shares)",
    )
    FilterConfig.objects.filter(key="debt_to_equity_max").update(
        value="2.0",
        description="Maximum long-term debt/equity ratio",
    )
    FilterConfig.objects.filter(key="free_cash_flow_min").update(
        description="Minimum cash flow per share (annual)",
    )
```

Add to the `operations` list (after the RenameField ops):

```python
migrations.RunPython(convert_volume_and_update_configs, reverse_code=reverse_convert),
```

Don't forget to add `from django.db.models import F` at the top of the migration file (inside the function is fine too).

- [ ] **Step 4: Run the migration**

```bash
docker compose exec web python manage.py migrate screener
```

- [ ] **Step 5: Verify the migration worked**

```bash
docker compose exec db psql -U thetagoblin -d thetagoblin -c "SELECT ticker, avg_volume_10d FROM screener_symbol WHERE avg_volume_10d IS NOT NULL ORDER BY avg_volume_10d DESC LIMIT 3;"
docker compose exec db psql -U thetagoblin -d thetagoblin -c "SELECT key, value, description FROM screener_filterconfig WHERE key IN ('min_avg_volume','debt_to_equity_max','free_cash_flow_min');"
```

Expected: NVDA volume should be ~194,197,680 (not 194.19), min_avg_volume should be 1500000, debt_to_equity_max should be 200.0.

- [ ] **Step 6: Commit**

```bash
git add screener/models.py screener/migrations/0012_*.py
git commit -m "refactor: rename fundamental fields to match yfinance semantics

Renames: cash_flow_per_share_annual -> free_cash_flow,
long_term_debt_to_equity_annual -> debt_to_equity,
ten_day_avg_trading_volume -> avg_volume_10d.
Converts volume from millions to raw shares.
Updates FilterConfig thresholds for new units."
```

---

## Chunk 2: Pipeline Rewiring and Test Updates

### Task 4: Update `candidates.py` with new field names

**Files:**
- Modify: `screener/services/candidates.py:18-21`

- [ ] **Step 1: Update the ORM filter field names**

Change the filter in `get_qualifying_symbols()`:

```python
    # OLD
    symbols = Symbol.objects.filter(
        market_cap__isnull=False,
        market_cap__gte=cfg["market_cap_min"],
        operating_margin__gt=cfg["operating_margin_min"],
        cash_flow_per_share_annual__gt=cfg["free_cash_flow_min"],
        long_term_debt_to_equity_annual__lt=cfg["debt_to_equity_max"],
        ten_day_avg_trading_volume__gte=cfg["min_avg_volume"],
    )

    # NEW
    symbols = Symbol.objects.filter(
        market_cap__isnull=False,
        market_cap__gte=cfg["market_cap_min"],
        operating_margin__gt=cfg["operating_margin_min"],
        free_cash_flow__gt=cfg["free_cash_flow_min"],
        debt_to_equity__lt=cfg["debt_to_equity_max"],
        avg_volume_10d__gte=cfg["min_avg_volume"],
    )
```

- [ ] **Step 2: Commit**

```bash
git add screener/services/candidates.py
git commit -m "refactor: update candidates filter to use renamed fields"
```

---

### Task 5: Update `admin.py` with new field names

**Files:**
- Modify: `screener/admin.py:18-21`

- [ ] **Step 1: Update `list_display`**

```python
    # OLD
    list_display = [
        "ticker", "name", "exchange_mic", "market_cap",
        "operating_margin", "ten_day_avg_trading_volume",
        "suppress_until", "fundamentals_updated_at",
    ]

    # NEW
    list_display = [
        "ticker", "name", "exchange_mic", "market_cap",
        "operating_margin", "avg_volume_10d",
        "suppress_until", "fundamentals_updated_at",
    ]
```

- [ ] **Step 2: Commit**

```bash
git add screener/admin.py
git commit -m "refactor: update admin list_display for renamed fields"
```

---

### Task 6: Update `load_symbols.py` with new field names

**Files:**
- Modify: `screener/management/commands/load_symbols.py:53-56`

- [ ] **Step 1: Update the `defaults` dict**

```python
    # OLD
    defaults={
        "exchange_mic": row.get("exchange_mic", "").strip(),
        "name": row.get("name", "").strip(),
        "market_cap": _parse_int(row.get("market_cap")),
        "operating_margin": _parse_float(row.get("operating_margin")),
        "cash_flow_per_share_annual": _parse_float(row.get("cash_flow_per_share_annual")),
        "long_term_debt_to_equity_annual": _parse_float(row.get("long_term_debt_to_equity_annual")),
        "ten_day_avg_trading_volume": _parse_float(row.get("ten_day_avg_trading_volume")),
    },

    # NEW
    defaults={
        "exchange_mic": row.get("exchange_mic", "").strip(),
        "name": row.get("name", "").strip(),
        "market_cap": _parse_int(row.get("market_cap")),
        "operating_margin": _parse_float(row.get("operating_margin")),
        "free_cash_flow": _parse_float(row.get("free_cash_flow")),
        "debt_to_equity": _parse_float(row.get("debt_to_equity")),
        "avg_volume_10d": _parse_float(row.get("avg_volume_10d")),
    },
```

- [ ] **Step 2: Commit**

```bash
git add screener/management/commands/load_symbols.py
git commit -m "refactor: update load_symbols for renamed fields"
```

---

### Task 7: Rewire `pull_fundamentals` to use yfinance

**Files:**
- Modify: `screener/management/commands/pull_fundamentals.py`

- [ ] **Step 1: Rewrite the command**

Replace the full file content:

```python
import logging
import time
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils.timezone import now

from screener.models import Symbol
from screener.services import yfinance_svc
from screener.services.yfinance_svc import YFinanceError
from screener.services.rate_limit import call_with_backoff

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Pull/refresh fundamentals from Yahoo Finance for stale symbols"

    def add_arguments(self, parser):
        parser.add_argument(
            "--stale-days",
            type=int,
            default=7,
            help="Only refresh symbols not updated in N days (default: 7)",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Max symbols to process — 0 means all (default: 0)",
        )

    def handle(self, *args, **options):
        stale_days = options["stale_days"]
        limit = options["limit"]
        delay = settings.YFINANCE_REQUEST_DELAY

        cutoff = now() - timedelta(days=stale_days)
        qs = Symbol.objects.filter(
            Q(fundamentals_updated_at__isnull=True) | Q(fundamentals_updated_at__lt=cutoff)
        ).order_by("ticker")

        if limit:
            qs = qs[:limit]

        symbols = list(qs)
        total = len(symbols)
        self.stdout.write(f"Processing {total} symbols (stale_days={stale_days}, delay={delay}s)")

        updated = 0
        failed = 0

        for i, sym in enumerate(symbols, 1):
            data = call_with_backoff(
                yfinance_svc.fetch_fundamentals,
                sym.ticker,
                retryable_exc=YFinanceError,
                label=sym.ticker,
            )

            if data is None:
                failed += 1
                if delay > 0:
                    time.sleep(delay)
                continue

            for field, value in data.items():
                if value is not None:
                    setattr(sym, field, value)
            sym.fundamentals_updated_at = now()
            sym.save()
            updated += 1

            if i % 50 == 0:
                self.stdout.write(f"  Progress: {i}/{total} (updated={updated}, failed={failed})")

            if delay > 0:
                time.sleep(delay)

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Updated: {updated}, Failed: {failed}, Total: {total}"
            )
        )
```

- [ ] **Step 2: Commit**

```bash
git add screener/management/commands/pull_fundamentals.py
git commit -m "feat: rewire pull_fundamentals to use yfinance instead of finnhub"
```

---

### Task 8: Remove `fetch_fundamentals` from finnhub_client

**Files:**
- Modify: `screener/services/finnhub_client.py`

- [ ] **Step 1: Remove `fetch_fundamentals` function and `RateLimitError` class**

Delete the `fetch_fundamentals` function (lines 23-52) from `finnhub_client.py`. Keep `RateLimitError` — it's still used by `fetch_earnings`.

Actually, check: `fetch_earnings` also uses `RateLimitError`, so keep it. Only delete `fetch_fundamentals`.

- [ ] **Step 2: Commit**

```bash
git add screener/services/finnhub_client.py
git commit -m "refactor: remove fetch_fundamentals from finnhub_client (moved to yfinance)"
```

---

### Task 9: Update all tests

**Files:**
- Modify: `screener/tests/test_pull_fundamentals.py`
- Modify: `screener/tests/test_finnhub_client.py`
- Modify: `screener/tests/test_candidates.py`
- Modify: `screener/tests/test_views.py`
- Modify: `screener/tests/test_live_options.py`
- Modify: `screener/tests/test_load_symbols.py`

- [ ] **Step 1: Update `test_pull_fundamentals.py`**

Replace full file:

```python
from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.core.management import call_command
from django.utils.timezone import now
from screener.models import Symbol


@override_settings(YFINANCE_REQUEST_DELAY=0)
class PullFundamentalsTest(TestCase):

    def setUp(self):
        self.sym = Symbol.objects.create(
            ticker="AAPL", exchange_mic="XNAS", name="Apple Inc"
        )

    @patch("screener.services.yfinance_svc.fetch_fundamentals")
    def test_updates_stale_symbol(self, mock_fetch):
        mock_fetch.return_value = {
            "market_cap": 3_000_000_000_000,
            "operating_margin": 0.30,
            "free_cash_flow": 106_000_000_000,
            "debt_to_equity": 102.63,
            "avg_volume_10d": 43_000_000,
        }
        call_command("pull_fundamentals")
        self.sym.refresh_from_db()
        self.assertEqual(self.sym.market_cap, 3_000_000_000_000)
        self.assertIsNotNone(self.sym.fundamentals_updated_at)

    @patch("screener.services.yfinance_svc.fetch_fundamentals")
    def test_skips_recently_updated(self, mock_fetch):
        mock_fetch.return_value = {
            "market_cap": 1_000_000_000, "operating_margin": 0.1,
            "free_cash_flow": 50_000_000, "debt_to_equity": 50.0,
            "avg_volume_10d": 1_000_000,
        }
        self.sym.fundamentals_updated_at = now()
        self.sym.save()
        call_command("pull_fundamentals", stale_days=7)
        mock_fetch.assert_not_called()

    @patch("screener.services.yfinance_svc.fetch_fundamentals")
    def test_handles_api_failure_gracefully(self, mock_fetch):
        mock_fetch.return_value = None
        call_command("pull_fundamentals")
        self.sym.refresh_from_db()
        self.assertIsNone(self.sym.fundamentals_updated_at)

    @patch("screener.services.yfinance_svc.fetch_fundamentals")
    def test_limit_option(self, mock_fetch):
        mock_fetch.return_value = {
            "market_cap": 1_000_000_000, "operating_margin": 0.1,
            "free_cash_flow": 50_000_000, "debt_to_equity": 50.0,
            "avg_volume_10d": 1_000_000,
        }
        Symbol.objects.create(ticker="MSFT", exchange_mic="XNAS", name="Microsoft")
        Symbol.objects.create(ticker="GOOG", exchange_mic="XNAS", name="Alphabet")
        call_command("pull_fundamentals", limit=1)
        self.assertEqual(mock_fetch.call_count, 1)
```

- [ ] **Step 2: Update `test_finnhub_client.py`**

Remove `FetchFundamentalsTest` class and its 3 test methods (`test_parses_valid_response`, `test_returns_none_on_http_error`, `test_handles_missing_market_cap`). Keep the `fetch_symbols` and `fetch_earnings` tests.

- [ ] **Step 3: Update `test_candidates.py`**

In all `Symbol.objects.create()` calls, replace:
- `cash_flow_per_share_annual=7.5` → `free_cash_flow=106_000_000_000`
- `cash_flow_per_share_annual=10.0` → `free_cash_flow=150_000_000_000`
- `long_term_debt_to_equity_annual=1.2` → `debt_to_equity=120.0`
- `long_term_debt_to_equity_annual=0.8` → `debt_to_equity=80.0`
- `ten_day_avg_trading_volume=5_000_000` → `avg_volume_10d=5_000_000`

- [ ] **Step 4: Update `test_views.py`**

Same field renames in all `Symbol.objects.create()` calls (lines 42-47, 107-112):
- `cash_flow_per_share_annual=7.5` → `free_cash_flow=106_000_000_000`
- `long_term_debt_to_equity_annual=1.2` → `debt_to_equity=120.0`
- `ten_day_avg_trading_volume=5_000_000` → `avg_volume_10d=5_000_000`

- [ ] **Step 5: Update `test_live_options.py`**

Same field renames in `Symbol.objects.create()` (lines 14-17):
- `cash_flow_per_share_annual=7.5` → `free_cash_flow=106_000_000_000`
- `long_term_debt_to_equity_annual=1.2` → `debt_to_equity=120.0`
- `ten_day_avg_trading_volume=5_000_000` → `avg_volume_10d=5_000_000`

- [ ] **Step 6: Update `test_load_symbols.py`**

Update CSV fieldnames list (line 16-17) and all row dicts to use new field names:
- `cash_flow_per_share_annual` → `free_cash_flow`
- `long_term_debt_to_equity_annual` → `debt_to_equity`
- `ten_day_avg_trading_volume` → `avg_volume_10d`

Also update the assertion on line 93: `self.assertIsNone(xyz.operating_margin)` — this stays the same since `operating_margin` wasn't renamed.

- [ ] **Step 7: Run full test suite**

```bash
docker compose exec web python manage.py test screener --verbosity=2
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add screener/tests/
git commit -m "test: update all tests for renamed fields and yfinance fundamentals"
```

---

### Task 10: Update or remove `scripts/build_universe.py`

**Files:**
- Modify: `scripts/build_universe.py`

This throwaway script uses Finnhub to build the initial universe CSV. It references old field names (`cash_flow_per_share_annual`, `long_term_debt_to_equity_annual`, `ten_day_avg_trading_volume`) and calls `finnhub_client.fetch_fundamentals`. Since we now load symbols from Nasdaq (via `scripts/load_nasdaq_symbols.py`) and pull fundamentals from yfinance, this script is **obsolete**.

- [ ] **Step 1: Delete the script**

```bash
rm scripts/build_universe.py
```

- [ ] **Step 2: Commit**

```bash
git add -A scripts/build_universe.py
git commit -m "chore: remove obsolete build_universe script (replaced by nasdaq loader + yfinance)"
```

---

### Task 11: Verify end-to-end with a live test

- [ ] **Step 1: Run fundamentals pull on a small batch**

```bash
docker compose exec web python manage.py pull_fundamentals --limit=5
```

Expected: 5 symbols updated, no errors.

- [ ] **Step 2: Verify stored data looks correct**

```bash
docker compose exec db psql -U thetagoblin -d thetagoblin -c "
SELECT ticker, market_cap, operating_margin, free_cash_flow, debt_to_equity, avg_volume_10d, fundamentals_updated_at
FROM screener_symbol
WHERE fundamentals_updated_at IS NOT NULL
ORDER BY fundamentals_updated_at DESC LIMIT 5;"
```

- [ ] **Step 3: Final commit with all changes**

```bash
git add -A
git status  # verify nothing unexpected
git commit -m "feat: complete yahoo fundamentals migration — replace finnhub with yfinance"
```
