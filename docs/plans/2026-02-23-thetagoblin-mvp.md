# ThetaGoblin MVP Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a local Django app that screens US equities for cash-secured put (CSP) candidates using fundamental filters, earnings exclusion, IV rank, and options chain analysis.

**Architecture:** Docker Compose (postgres:17 + Django 5.x). Single Django app `screener` with models for Symbol, EarningsDate, OptionsSnapshot, IVRank, FilterConfig. Data fetching modularized behind service modules (finnhub.py, yfinance_svc.py). Management commands for batch jobs with resume-from-failure. APScheduler for weekly cron. Single candidates view with refresh.

**Tech Stack:** Python 3.12, Django 5.x, PostgreSQL 17, Docker Compose, finnhub (symbols/fundamentals/earnings), yfinance (options/IV), APScheduler, py_vollib or scipy for Black-Scholes delta, python-dotenv.

---

## Task 1: Docker Compose + Django Scaffold + .env Wiring

**Goal:** Running Django dev server in Docker with hot reload, connected to PostgreSQL, all config from environment variables.

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `requirements.txt`
- Create: `thetagoblin/__init__.py`
- Create: `thetagoblin/settings.py`
- Create: `thetagoblin/urls.py`
- Create: `thetagoblin/wsgi.py`
- Create: `thetagoblin/asgi.py`
- Create: `manage.py`
- Create: `screener/__init__.py`
- Create: `screener/apps.py`
- Modify: `.env` (add all required vars)
- Modify: `.gitignore` (ensure .env stays ignored)

### Step 1: Create `.env` with all config

```env
# Django
DJANGO_SECRET_KEY=change-me-in-production
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0

# Database
POSTGRES_DB=thetagoblin
POSTGRES_USER=thetagoblin
POSTGRES_PASSWORD=thetagoblin_dev
DATABASE_URL=postgres://thetagoblin:thetagoblin_dev@db:5432/thetagoblin

# API Keys
FINNHUB_TOKEN=<your-token-here>
```

### Step 2: Create `requirements.txt`

```
Django>=5.0,<6.0
psycopg[binary]>=3.1,<4.0
dj-database-url>=2.1,<3.0
python-dotenv>=1.0,<2.0
finnhub-python>=2.4,<3.0
yfinance>=0.2,<1.0
apscheduler>=3.10,<4.0
scipy>=1.11,<2.0
```

### Step 3: Create `Dockerfile`

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
```

### Step 4: Create `docker-compose.yml`

Two services: `db` (postgres:17) and `web` (Django). Web mounts the project directory as a volume for hot reload. Web depends on db. All env from `.env`.

```yaml
services:
  db:
    image: postgres:17
    env_file: .env
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  web:
    build: .
    env_file: .env
    volumes:
      - .:/app
    ports:
      - "8000:8000"
    depends_on:
      - db

volumes:
  pgdata:
```

### Step 5: Create Django project scaffold

Create `manage.py`, `thetagoblin/settings.py`, `thetagoblin/urls.py`, `thetagoblin/wsgi.py`, `thetagoblin/asgi.py`.

**settings.py key points:**
- Load `.env` with `dotenv.load_dotenv()` at top
- `SECRET_KEY` from `os.environ["DJANGO_SECRET_KEY"]`
- `DEBUG` from env
- `ALLOWED_HOSTS` from env (comma-split)
- `DATABASES` via `dj_database_url.config(default=os.environ["DATABASE_URL"])`
- `INSTALLED_APPS` includes `screener`
- `TIME_ZONE = "America/New_York"` (market-relevant)

### Step 6: Create `screener` app skeleton

Create `screener/__init__.py`, `screener/apps.py`, `screener/models.py` (empty for now), `screener/admin.py`, `screener/views.py`.

### Step 7: Verify it runs

```bash
docker compose up --build
```

Expected: Django dev server starts, connects to PostgreSQL, serves the default welcome page at `http://localhost:8000`.

### Step 8: Commit

```bash
git add Dockerfile docker-compose.yml requirements.txt manage.py \
    thetagoblin/ screener/ .gitignore
git commit -m "feat: Docker Compose scaffold with Django + PostgreSQL"
```

**Do NOT commit `.env`** — it should be in `.gitignore`.

---

## Task 2: Models + Migrations

**Goal:** All five data models created, migrated, and verified in the database.

**Files:**
- Create: `screener/models.py` (all models)
- Create: `screener/tests/__init__.py`
- Create: `screener/tests/test_models.py`

### Step 1: Write model tests

Test file: `screener/tests/test_models.py`

Tests to write:
- `test_symbol_str_returns_ticker` — create a Symbol, assert `str()` returns ticker
- `test_symbol_unique_ticker` — assert IntegrityError on duplicate ticker
- `test_earnings_date_fk_cascade` — delete symbol cascades to EarningsDate
- `test_options_snapshot_fk_cascade` — delete symbol cascades to OptionsSnapshot
- `test_iv_rank_fk_cascade` — delete symbol cascades to IVRank
- `test_filter_config_unique_key` — assert IntegrityError on duplicate key
- `test_filter_config_get_typed_value` — test the `typed_value` property returns int/float/bool correctly
- `test_filter_config_get_value_helper` — test the `get_value(key)` classmethod returns typed value

### Step 2: Run tests to verify they fail

```bash
docker compose exec web python manage.py test screener.tests.test_models -v2
```

Expected: ImportError or AttributeError (models don't exist yet).

### Step 3: Implement models in `screener/models.py`

```python
class Symbol(models.Model):
    ticker = models.CharField(max_length=10, unique=True, db_index=True)
    exchange_mic = models.CharField(max_length=10)
    name = models.CharField(max_length=255)
    market_cap = models.BigIntegerField(null=True, blank=True)
    operating_margin = models.FloatField(null=True, blank=True)
    cash_flow_per_share_annual = models.FloatField(null=True, blank=True)
    long_term_debt_to_equity_annual = models.FloatField(null=True, blank=True)
    ten_day_avg_trading_volume = models.FloatField(null=True, blank=True)
    fundamentals_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["ticker"]

    def __str__(self):
        return self.ticker


class EarningsDate(models.Model):
    symbol = models.ForeignKey(Symbol, on_delete=models.CASCADE, related_name="earnings_dates")
    report_date = models.DateField()
    source = models.CharField(max_length=50, default="finnhub")
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["symbol", "report_date"]
        ordering = ["report_date"]


class OptionsSnapshot(models.Model):
    symbol = models.ForeignKey(Symbol, on_delete=models.CASCADE, related_name="options_snapshots")
    snapshot_date = models.DateField()
    expiry_date = models.DateField()
    dte_at_snapshot = models.IntegerField()
    strike = models.DecimalField(max_digits=10, decimal_places=2)
    spot_price = models.DecimalField(max_digits=10, decimal_places=2)
    implied_volatility = models.FloatField(null=True, blank=True)
    bid = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    ask = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    spread_pct = models.FloatField(null=True, blank=True)
    open_interest = models.IntegerField(null=True, blank=True)
    volume = models.IntegerField(null=True, blank=True)
    delta = models.FloatField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["symbol", "snapshot_date"]),
            models.Index(fields=["expiry_date"]),
        ]
        ordering = ["symbol", "expiry_date", "strike"]


class IVRank(models.Model):
    symbol = models.ForeignKey(Symbol, on_delete=models.CASCADE, related_name="iv_ranks")
    computed_date = models.DateField()
    iv_rank = models.FloatField(help_text="0-100 scale")
    iv_percentile = models.FloatField(null=True, blank=True)
    weeks_of_history = models.IntegerField(default=0)
    is_reliable = models.BooleanField(default=False, help_text="True when >= 52 weeks of history")

    class Meta:
        unique_together = ["symbol", "computed_date"]
        ordering = ["-computed_date"]


class FilterConfig(models.Model):
    VALUE_TYPES = [
        ("int", "Integer"),
        ("float", "Float"),
        ("bool", "Boolean"),
    ]

    key = models.CharField(max_length=100, unique=True)
    value = models.CharField(max_length=100)
    value_type = models.CharField(max_length=10, choices=VALUE_TYPES, default="float")
    description = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def typed_value(self):
        if self.value_type == "int":
            return int(self.value)
        elif self.value_type == "float":
            return float(self.value)
        elif self.value_type == "bool":
            return self.value.lower() in ("true", "1", "yes")
        return self.value

    @classmethod
    def get_value(cls, key):
        """Get typed value for a config key. Raises DoesNotExist if missing."""
        return cls.objects.get(key=key).typed_value

    def __str__(self):
        return f"{self.key} = {self.value}"
```

### Step 4: Generate and run migrations

```bash
docker compose exec web python manage.py makemigrations screener
docker compose exec web python manage.py migrate
```

### Step 5: Run tests to verify they pass

```bash
docker compose exec web python manage.py test screener.tests.test_models -v2
```

Expected: All tests PASS.

### Step 6: Commit

```bash
git add screener/models.py screener/migrations/ screener/tests/
git commit -m "feat: add Symbol, EarningsDate, OptionsSnapshot, IVRank, FilterConfig models"
```

---

## Task 3: FilterConfig Seed Data Migration

**Goal:** A data migration that populates FilterConfig with all default threshold values so the pipeline works out of the box.

**Files:**
- Create: `screener/migrations/0002_seed_filterconfig.py` (generated, then hand-edited)
- Create: `screener/tests/test_seed.py`

### Step 1: Write test for seed data

Test file: `screener/tests/test_seed.py`

```python
from django.test import TestCase
from screener.models import FilterConfig


class FilterConfigSeedTest(TestCase):
    """Migrations run automatically in test DB, so seeds should exist."""

    def test_all_default_keys_exist(self):
        expected_keys = [
            "market_cap_min", "operating_margin_min", "free_cash_flow_min",
            "avg_daily_dollar_volume_min", "debt_to_equity_max",
            "earnings_exclusion_days", "iv_rank_min", "iv_rank_max",
            "iv_min", "iv_max", "delta_target_min", "delta_target_max",
            "otm_pct_target", "expiry_dte_min", "expiry_dte_max",
            "risk_free_rate",
        ]
        for key in expected_keys:
            self.assertTrue(
                FilterConfig.objects.filter(key=key).exists(),
                f"Missing seed key: {key}",
            )

    def test_market_cap_min_value(self):
        val = FilterConfig.get_value("market_cap_min")
        self.assertEqual(val, 10_000_000_000)

    def test_risk_free_rate_value(self):
        val = FilterConfig.get_value("risk_free_rate")
        self.assertAlmostEqual(val, 0.043)
```

### Step 2: Create data migration

```bash
docker compose exec web python manage.py makemigrations screener --empty -n seed_filterconfig
```

Then edit the generated file to populate all 16 keys:

```python
def seed_filter_config(apps, schema_editor):
    FilterConfig = apps.get_model("screener", "FilterConfig")
    defaults = [
        ("market_cap_min", "10000000000", "int", "Minimum market cap in USD"),
        ("operating_margin_min", "0.0", "float", "Minimum operating margin (0.0 = breakeven)"),
        ("free_cash_flow_min", "0", "float", "Minimum cash flow per share (annual)"),
        ("avg_daily_dollar_volume_min", "100000000", "int", "Minimum 10-day avg dollar volume"),
        ("debt_to_equity_max", "2.0", "float", "Maximum long-term debt/equity ratio"),
        ("earnings_exclusion_days", "50", "int", "Exclude tickers with earnings within N calendar days"),
        ("iv_rank_min", "70", "float", "Minimum IV rank (0-100)"),
        ("iv_rank_max", "90", "float", "Maximum IV rank (0-100)"),
        ("iv_min", "0.20", "float", "Minimum implied volatility"),
        ("iv_max", "0.40", "float", "Maximum implied volatility"),
        ("delta_target_min", "0.15", "float", "Minimum abs(delta) for candidate puts"),
        ("delta_target_max", "0.30", "float", "Maximum abs(delta) for candidate puts"),
        ("otm_pct_target", "0.175", "float", "Target OTM percentage (17.5%)"),
        ("expiry_dte_min", "30", "int", "Minimum days to expiry"),
        ("expiry_dte_max", "45", "int", "Maximum days to expiry"),
        ("risk_free_rate", "0.043", "float", "3-month T-bill rate for Black-Scholes delta calc"),
    ]
    for key, value, value_type, description in defaults:
        FilterConfig.objects.get_or_create(
            key=key,
            defaults={"value": value, "value_type": value_type, "description": description},
        )


def reverse(apps, schema_editor):
    FilterConfig = apps.get_model("screener", "FilterConfig")
    FilterConfig.objects.all().delete()
```

### Step 3: Run migration, then tests

```bash
docker compose exec web python manage.py migrate
docker compose exec web python manage.py test screener.tests.test_seed -v2
```

Expected: All PASS.

### Step 4: Commit

```bash
git add screener/migrations/0002_seed_filterconfig.py screener/tests/test_seed.py
git commit -m "feat: seed FilterConfig with 16 default threshold values"
```

---

## Task 4: Standalone Script to Build Universe from Finnhub

**Goal:** A standalone Python script (`scripts/build_universe.py`) that pulls symbols from Finnhub (XNAS + XNYS), fetches fundamentals for the first 100 from each exchange, filters to market_cap > 1B, and writes a CSV. Plus a Django management command to load that CSV into the Symbol table.

**Files:**
- Create: `scripts/build_universe.py`
-  use root `.env`
- Create: `screener/management/__init__.py`
- Create: `screener/management/commands/__init__.py`
- Create: `screener/management/commands/load_symbols.py`
- Create: `screener/tests/test_load_symbols.py`

### Step 1: Create `scripts/build_universe.py`

Standalone script (not Django). Uses `python-dotenv` to load `FINNHUB_TOKEN` from the `.env` file in the project root (`../env` relative to `scripts/`). The token **must be included as a query parameter in every Finnhub API call**.

**Token loading pattern (at top of script):**
```python
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (one level up from scripts/)
load_dotenv(Path(__file__).parent.parent / ".env")

FINNHUB_TOKEN = os.environ["FINNHUB_TOKEN"]  # raises KeyError if missing
BASE_URL = "https://finnhub.io/api/v1"
```

**Every request must include token in params:**
```python
# Symbols endpoint
resp = requests.get(
    f"{BASE_URL}/stock/symbol",
    params={"exchange": "US", "mic": mic, "token": FINNHUB_TOKEN},
    timeout=10,
)

# Fundamentals endpoint
resp = requests.get(
    f"{BASE_URL}/stock/metric",
    params={"symbol": ticker, "metric": "all", "token": FINNHUB_TOKEN},
    timeout=10,
)
```

**Key behavior:**
- Calls `GET /api/v1/stock/symbol?exchange=US&mic=XNAS&token=...` and `&mic=XNYS&token=...`
- For the first 100 symbols from each exchange, calls `GET /api/v1/stock/metric?symbol={ticker}&metric=all&token=...`
- **Rate limiting:** 1-second delay (`time.sleep(1.0)`) between each fundamentals call. This stays well under Finnhub's 60 calls/min free tier limit.
- **Error handling:** try/except around each API call, log and skip on failure, continue to next symbol.
- Extracts from the `metric` response: `marketCapitalization` (Finnhub returns in millions — multiply by 1,000,000), `operatingMarginAnnual`, `cashFlowPerShareAnnual`, `10DayAverageTradingVolume`, `longTermDebt/equityAnnual`
- Filters: keep only rows where `market_cap > 1_000_000_000`
- Dollar volume computation: `10DayAverageTradingVolume * current_price` — note Finnhub's metric endpoint doesn't return price directly. Use the `marketCapitalization` and basic metrics. For the seed script, filtering on market cap > 1B is sufficient; dollar volume filtering happens in the pipeline.
- Writes CSV with columns: `ticker, exchange_mic, name, market_cap, operating_margin, cash_flow_per_share_annual, long_term_debt_to_equity_annual, ten_day_avg_trading_volume`
- Uses `argparse` for output path, with default `data/universe.csv`
- Progress: prints count every 10 symbols

**Finnhub metric response path:**
```python
data = response.json()
metrics = data.get("metric", {})
market_cap = metrics.get("marketCapitalization")  # in millions — multiply by 1_000_000
operating_margin = metrics.get("operatingMarginAnnual")
cash_flow = metrics.get("cashFlowPerShareAnnual")
volume_10d = metrics.get("10DayAverageTradingVolume")
debt_equity = metrics.get("longTermDebt/equityAnnual")
```

**Symbol name** comes from the symbols endpoint response field `description` (not `name`).

### Step 2: Write test for load_symbols command

```python
class LoadSymbolsTest(TestCase):
    def setUp(self):
        # Create a small test CSV in a temp file
        self.csv_content = "ticker,exchange_mic,name,market_cap,operating_margin,..."
        ...

    def test_load_creates_symbols(self):
        call_command("load_symbols", self.csv_path)
        self.assertEqual(Symbol.objects.count(), N)

    def test_load_is_idempotent(self):
        call_command("load_symbols", self.csv_path)
        call_command("load_symbols", self.csv_path)
        self.assertEqual(Symbol.objects.count(), N)  # no duplicates

    def test_load_updates_existing(self):
        # If ticker exists, update fundamentals, don't create duplicate
```

### Step 3: Implement `load_symbols` management command

```python
# screener/management/commands/load_symbols.py
class Command(BaseCommand):
    help = "Load symbols from CSV into the Symbol table"

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str)

    def handle(self, *args, **options):
        # Read CSV, for each row: update_or_create Symbol by ticker
        # Report: created N, updated M
```

Uses `Symbol.objects.update_or_create(ticker=row["ticker"], defaults={...})` for idempotency.

### Step 4: Run the script and load command

```bash
# Run standalone script (from host, not Docker)
cd scripts && python build_universe.py

# Load into Django DB
docker compose exec web python manage.py load_symbols data/universe.csv
```

### Step 5: Verify

```bash
docker compose exec web python manage.py shell -c "from screener.models import Symbol; print(Symbol.objects.count())"
```

Expected: prints the number of symbols loaded (should be in the range of 50-150 depending on how many pass the market_cap filter).

### Step 6: Commit

```bash
git add scripts/ screener/management/ screener/tests/test_load_symbols.py data/
git commit -m "feat: Finnhub universe builder script + load_symbols management command"
```

---

## Task 5: Fundamentals Pull/Refresh Job

**Goal:** A management command `pull_fundamentals` that refreshes fundamentals from Finnhub for all symbols in the database, with resume-from-failure logic.

**Files:**
- Create: `screener/services/__init__.py`
- Create: `screener/services/finnhub_client.py`
- Create: `screener/management/commands/pull_fundamentals.py`
- Create: `screener/tests/test_finnhub_client.py`
- Create: `screener/tests/test_pull_fundamentals.py`

### Step 1: Write tests for finnhub_client

Test file: `screener/tests/test_finnhub_client.py`

- `test_fetch_fundamentals_parses_response` — mock the HTTP call, assert it returns a dict with expected keys
- `test_fetch_fundamentals_handles_error` — mock a 429/500, assert it returns None (not raises)
- `test_fetch_fundamentals_handles_missing_metrics` — mock a response with missing fields, assert None values

### Step 2: Implement `screener/services/finnhub_client.py`

**Design principle:** This is a thin wrapper. Easy to swap for a different provider later.

```python
import logging
import os
import time
import requests

logger = logging.getLogger(__name__)

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"


def get_token():
    token = os.environ.get("FINNHUB_TOKEN")
    if not token:
        raise ValueError("FINNHUB_TOKEN not set in environment")
    return token


def fetch_fundamentals(ticker: str) -> dict | None:
    """Fetch fundamental metrics for a single ticker.
    Returns dict with keys: market_cap, operating_margin, cash_flow_per_share_annual,
    long_term_debt_to_equity_annual, ten_day_avg_trading_volume.
    Returns None on any error.
    """
    try:
        resp = requests.get(
            f"{FINNHUB_BASE_URL}/stock/metric",
            params={"symbol": ticker, "metric": "all", "token": get_token()},
            timeout=10,
        )
        resp.raise_for_status()
        metrics = resp.json().get("metric", {})
        raw_cap = metrics.get("marketCapitalization")
        return {
            "market_cap": int(raw_cap * 1_000_000) if raw_cap else None,
            "operating_margin": metrics.get("operatingMarginAnnual"),
            "cash_flow_per_share_annual": metrics.get("cashFlowPerShareAnnual"),
            "long_term_debt_to_equity_annual": metrics.get("longTermDebt/equityAnnual"),
            "ten_day_avg_trading_volume": metrics.get("10DayAverageTradingVolume"),
        }
    except Exception:
        logger.exception("Failed to fetch fundamentals for %s", ticker)
        return None


def fetch_symbols(exchange_mic: str) -> list[dict]:
    """Fetch list of symbols for an exchange. Returns list of {ticker, name, type, mic}."""
    try:
        resp = requests.get(
            f"{FINNHUB_BASE_URL}/stock/symbol",
            params={"exchange": "US", "mic": exchange_mic, "token": get_token()},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        logger.exception("Failed to fetch symbols for %s", exchange_mic)
        return []
```

### Step 3: Write tests for pull_fundamentals command

- `test_skips_recently_updated` — symbol updated today should be skipped
- `test_updates_stale_symbol` — symbol updated 30+ days ago should be refreshed
- `test_handles_api_failure_gracefully` — if fetch returns None, symbol is skipped, command continues
- `test_updates_fundamentals_updated_at` — after success, timestamp is set

### Step 4: Implement `pull_fundamentals` management command

```python
class Command(BaseCommand):
    help = "Pull/refresh fundamentals from Finnhub for all symbols"

    def add_arguments(self, parser):
        parser.add_argument("--stale-days", type=int, default=7,
                            help="Only refresh symbols not updated in N days")
        parser.add_argument("--limit", type=int, default=0,
                            help="Max symbols to process (0=all)")
        parser.add_argument("--delay", type=float, default=1.0,
                            help="Seconds between API calls")

    def handle(self, *args, **options):
        cutoff = now() - timedelta(days=options["stale_days"])
        symbols = Symbol.objects.filter(
            Q(fundamentals_updated_at__isnull=True) | Q(fundamentals_updated_at__lt=cutoff)
        ).order_by("ticker")

        if options["limit"]:
            symbols = symbols[:options["limit"]]

        updated, skipped, failed = 0, 0, 0
        for sym in symbols:
            data = finnhub_client.fetch_fundamentals(sym.ticker)
            if data is None:
                failed += 1
                time.sleep(options["delay"])
                continue

            for field, value in data.items():
                if value is not None:
                    setattr(sym, field, value)
            sym.fundamentals_updated_at = now()
            sym.save()
            updated += 1
            time.sleep(options["delay"])

        self.stdout.write(f"Updated: {updated}, Failed: {failed}")
```

**Resume logic:** The `fundamentals_updated_at` filter means re-running the command picks up where it left off — successfully updated symbols won't be re-fetched until they're stale again.

### Step 5: Run tests, then verify with a real call

```bash
docker compose exec web python manage.py test screener.tests.test_finnhub_client screener.tests.test_pull_fundamentals -v2
docker compose exec web python manage.py pull_fundamentals --limit 5
```

### Step 6: Commit

```bash
git add screener/services/ screener/management/commands/pull_fundamentals.py \
    screener/tests/test_finnhub_client.py screener/tests/test_pull_fundamentals.py
git commit -m "feat: Finnhub fundamentals service + pull_fundamentals command with resume"
```

---

## Task 6: Earnings Calendar Pull

**Goal:** A service function and management command to pull upcoming earnings dates from Finnhub and store them in EarningsDate.

**Files:**
- Modify: `screener/services/finnhub_client.py` (add `fetch_earnings`)
- Create: `screener/management/commands/pull_earnings.py`
- Create: `screener/tests/test_pull_earnings.py`

### Step 1: Write tests

- `test_fetch_earnings_parses_response` — mock Finnhub earnings calendar, assert list of dicts
- `test_pull_earnings_creates_records` — command creates EarningsDate rows
- `test_pull_earnings_idempotent` — running twice doesn't create duplicates (unique_together on symbol+date)
- `test_pull_earnings_only_stores_known_symbols` — earnings for tickers not in Symbol table are skipped

### Step 2: Add `fetch_earnings` to finnhub_client

```python
def fetch_earnings(from_date: str, to_date: str) -> list[dict]:
    """Fetch earnings calendar. Returns list of {symbol, date, ...}.
    Dates in YYYY-MM-DD format.
    """
    try:
        resp = requests.get(
            f"{FINNHUB_BASE_URL}/calendar/earnings",
            params={"from": from_date, "to": to_date, "token": get_token()},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("earningsCalendar", [])
    except Exception:
        logger.exception("Failed to fetch earnings calendar")
        return []
```

### Step 3: Implement management command

```python
class Command(BaseCommand):
    help = "Pull earnings calendar from Finnhub"

    def add_arguments(self, parser):
        parser.add_argument("--weeks-ahead", type=int, default=8,
                            help="How many weeks ahead to pull earnings")

    def handle(self, *args, **options):
        today = date.today()
        end = today + timedelta(weeks=options["weeks_ahead"])
        earnings = finnhub_client.fetch_earnings(
            today.isoformat(), end.isoformat()
        )

        known_tickers = set(Symbol.objects.values_list("ticker", flat=True))
        created, skipped = 0, 0

        for entry in earnings:
            ticker = entry.get("symbol")
            report_date = entry.get("date")
            if not ticker or not report_date or ticker not in known_tickers:
                skipped += 1
                continue
            symbol = Symbol.objects.get(ticker=ticker)
            _, was_created = EarningsDate.objects.update_or_create(
                symbol=symbol, report_date=report_date,
                defaults={"source": "finnhub"},
            )
            if was_created:
                created += 1

        self.stdout.write(f"Created: {created}, Skipped: {skipped}")
```

Note: Finnhub's earnings calendar is a single API call (not per-symbol), so no rate limiting concern here.

### Step 4: Run tests, then verify

```bash
docker compose exec web python manage.py test screener.tests.test_pull_earnings -v2
docker compose exec web python manage.py pull_earnings --weeks-ahead 8
```

### Step 5: Commit

```bash
git add screener/services/finnhub_client.py \
    screener/management/commands/pull_earnings.py \
    screener/tests/test_pull_earnings.py
git commit -m "feat: earnings calendar pull from Finnhub"
```

---

## Task 7: Options Data Pull + Delta Calculation

**Goal:** A service module for yfinance options data + Black-Scholes delta computation, and a management command to pull options snapshots for qualifying symbols.

**Files:**
- Create: `screener/services/yfinance_svc.py`
- Create: `screener/services/options_math.py`
- Create: `screener/services/candidates.py`
- Create: `screener/management/commands/pull_options.py`
- Create: `screener/tests/test_options_math.py`
- Create: `screener/tests/test_yfinance_svc.py`
- Create: `screener/tests/test_pull_options.py`

### Step 1: Write delta calculation tests

File: `screener/tests/test_options_math.py`

```python
class BlackScholesDeltaTest(TestCase):
    def test_atm_put_delta_near_minus_half(self):
        # ATM put: spot=100, strike=100, 30 DTE, 25% vol, 4.3% rate
        delta = compute_put_delta(spot=100, strike=100, dte=30, vol=0.25, rate=0.043)
        self.assertAlmostEqual(delta, -0.48, places=1)

    def test_deep_otm_put_delta_near_zero(self):
        delta = compute_put_delta(spot=100, strike=70, dte=30, vol=0.25, rate=0.043)
        self.assertAlmostEqual(delta, 0.0, places=1)

    def test_itm_put_delta_near_minus_one(self):
        delta = compute_put_delta(spot=100, strike=130, dte=30, vol=0.25, rate=0.043)
        self.assertAlmostEqual(delta, -1.0, places=1)

    def test_zero_dte_raises_or_handles(self):
        # Edge case: DTE=0 should not crash
        delta = compute_put_delta(spot=100, strike=95, dte=0, vol=0.25, rate=0.043)
        self.assertIsNotNone(delta)
```

### Step 2: Implement `screener/services/options_math.py`

```python
import math
from scipy.stats import norm


def compute_put_delta(spot: float, strike: float, dte: int,
                      vol: float, rate: float) -> float:
    """Black-Scholes put delta. Returns negative value (e.g., -0.25)."""
    if dte <= 0 or vol <= 0 or spot <= 0:
        return 0.0

    T = dte / 365.0
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol**2) * T) / (vol * math.sqrt(T))
    return norm.cdf(d1) - 1.0
```

### Step 3: Write yfinance service tests (mocked)

- `test_fetch_options_chain_returns_dataframe` — mock yfinance Ticker, assert structure
- `test_fetch_options_chain_handles_error` — mock exception, returns None

### Step 4: Implement `screener/services/yfinance_svc.py`

```python
import logging
import yfinance as yf

logger = logging.getLogger(__name__)


def get_expiry_dates(ticker: str) -> list[str]:
    """Return list of available expiry dates for a ticker."""
    try:
        t = yf.Ticker(ticker)
        return list(t.options)
    except Exception:
        logger.exception("Failed to get expiry dates for %s", ticker)
        return []


def get_puts_chain(ticker: str, expiry: str) -> list[dict] | None:
    """Fetch puts chain for a ticker and expiry. Returns list of dicts or None."""
    try:
        t = yf.Ticker(ticker)
        chain = t.option_chain(expiry)
        spot = t.info.get("currentPrice") or t.info.get("regularMarketPrice")
        puts = chain.puts
        rows = []
        for _, row in puts.iterrows():
            rows.append({
                "strike": float(row["strike"]),
                "bid": float(row.get("bid", 0)),
                "ask": float(row.get("ask", 0)),
                "implied_volatility": float(row.get("impliedVolatility", 0)),
                "open_interest": int(row.get("openInterest", 0) or 0),
                "volume": int(row.get("volume", 0) or 0),
                "spot_price": spot,
            })
        return rows
    except Exception:
        logger.exception("Failed to get puts chain for %s exp %s", ticker, expiry)
        return None
```

### Step 5: Implement `screener/services/candidates.py`

```python
from datetime import date, timedelta
from django.db.models import Q
from screener.models import Symbol, EarningsDate, FilterConfig


def get_qualifying_symbols() -> list[Symbol]:
    """Return symbols passing all fundamental + earnings filters."""
    cfg = {fc.key: fc.typed_value for fc in FilterConfig.objects.all()}

    symbols = Symbol.objects.filter(
        market_cap__gte=cfg["market_cap_min"],
        operating_margin__gt=cfg["operating_margin_min"],
        cash_flow_per_share_annual__gt=cfg["free_cash_flow_min"],
        long_term_debt_to_equity_annual__lt=cfg["debt_to_equity_max"],
    ).exclude(
        market_cap__isnull=True,
    )

    # Exclude symbols with earnings within exclusion window
    exclusion_cutoff = date.today() + timedelta(days=cfg["earnings_exclusion_days"])
    tickers_with_upcoming_earnings = EarningsDate.objects.filter(
        report_date__gte=date.today(),
        report_date__lte=exclusion_cutoff,
    ).values_list("symbol__ticker", flat=True)

    symbols = symbols.exclude(ticker__in=tickers_with_upcoming_earnings)
    return list(symbols)
```

### Step 6: Implement `pull_options` management command

```python
class Command(BaseCommand):
    help = "Pull options snapshots for qualifying symbols"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--delay", type=float, default=0.5,
                            help="Seconds between yfinance calls")

    def handle(self, *args, **options):
        cfg = {fc.key: fc.typed_value for fc in FilterConfig.objects.all()}
        symbols = get_qualifying_symbols()
        if options["limit"]:
            symbols = symbols[:options["limit"]]

        today = date.today()
        dte_min = cfg["expiry_dte_min"]
        dte_max = cfg["expiry_dte_max"]
        delta_store_min = 0.10  # wider band for storage
        delta_store_max = 0.35
        rate = cfg["risk_free_rate"]

        total_saved = 0
        for sym in symbols:
            expiries = yfinance_svc.get_expiry_dates(sym.ticker)
            for expiry_str in expiries:
                expiry = date.fromisoformat(expiry_str)
                dte = (expiry - today).days
                if dte < dte_min or dte > dte_max:
                    continue

                puts = yfinance_svc.get_puts_chain(sym.ticker, expiry_str)
                if not puts:
                    continue

                for put in puts:
                    vol = put["implied_volatility"]
                    spot = put["spot_price"]
                    if not spot or not vol:
                        continue

                    delta = compute_put_delta(
                        spot=spot, strike=put["strike"],
                        dte=dte, vol=vol, rate=rate
                    )

                    if abs(delta) < delta_store_min or abs(delta) > delta_store_max:
                        continue

                    spread_pct = None
                    if put["bid"] and put["bid"] > 0:
                        spread_pct = (put["ask"] - put["bid"]) / put["bid"]

                    OptionsSnapshot.objects.update_or_create(
                        symbol=sym,
                        snapshot_date=today,
                        expiry_date=expiry,
                        strike=put["strike"],
                        defaults={
                            "dte_at_snapshot": dte,
                            "spot_price": spot,
                            "implied_volatility": vol,
                            "bid": put["bid"],
                            "ask": put["ask"],
                            "spread_pct": spread_pct,
                            "open_interest": put["open_interest"],
                            "volume": put["volume"],
                            "delta": delta,
                        },
                    )
                    total_saved += 1

                time.sleep(options["delay"])

        self.stdout.write(f"Saved {total_saved} option snapshots")
```

### Step 7: Run tests

```bash
docker compose exec web python manage.py test screener.tests.test_options_math \
    screener.tests.test_yfinance_svc screener.tests.test_pull_options -v2
```

### Step 8: Commit

```bash
git add screener/services/ screener/management/commands/pull_options.py \
    screener/tests/test_options_math.py screener/tests/test_yfinance_svc.py \
    screener/tests/test_pull_options.py
git commit -m "feat: options data pull with Black-Scholes delta + candidate filtering"
```

---

## Task 8: Pipeline Orchestration (Two Management Commands)

**Goal:** Two top-level management commands that orchestrate the full pipeline, plus APScheduler integration for automated weekly runs.

**Files:**
- Create: `screener/management/commands/run_fundamentals_pipeline.py`
- Create: `screener/management/commands/run_options_pipeline.py`
- Create: `screener/scheduler.py`
- Modify: `screener/apps.py` (start scheduler on app ready)
- Create: `screener/tests/test_scheduler.py`

### Step 1: Implement `run_fundamentals_pipeline`

Orchestrates: pull_fundamentals + pull_earnings in sequence.

```python
class Command(BaseCommand):
    help = "Run the full fundamentals refresh pipeline"

    def handle(self, *args, **options):
        self.stdout.write("=== Starting fundamentals pipeline ===")
        call_command("pull_fundamentals", stdout=self.stdout, stderr=self.stderr)
        call_command("pull_earnings", stdout=self.stdout, stderr=self.stderr)
        self.stdout.write("=== Fundamentals pipeline complete ===")
```

### Step 2: Implement `run_options_pipeline`

Orchestrates: pull_options (which internally calls get_qualifying_symbols).

```python
class Command(BaseCommand):
    help = "Run the options analysis pipeline"

    def handle(self, *args, **options):
        self.stdout.write("=== Starting options pipeline ===")
        call_command("pull_options", stdout=self.stdout, stderr=self.stderr)
        self.stdout.write("=== Options pipeline complete ===")
```

### Step 3: Implement APScheduler integration

File: `screener/scheduler.py`

```python
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django.core.management import call_command

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def start():
    if scheduler.running:
        return

    # Fundamentals + earnings: weekly, Friday 6 PM ET (after market close)
    scheduler.add_job(
        lambda: call_command("run_fundamentals_pipeline"),
        trigger=CronTrigger(day_of_week="fri", hour=18, minute=0),
        id="fundamentals_pipeline",
        replace_existing=True,
    )

    # Options: weekly, Friday 7 PM ET (after fundamentals)
    scheduler.add_job(
        lambda: call_command("run_options_pipeline"),
        trigger=CronTrigger(day_of_week="fri", hour=19, minute=0),
        id="options_pipeline",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started with weekly jobs")
```

### Step 4: Wire scheduler into Django app startup

Modify `screener/apps.py`:

```python
class ScreenerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "screener"

    def ready(self):
        import os
        # Only start scheduler in the main runserver process, not in management commands
        if os.environ.get("RUN_SCHEDULER", "true").lower() == "true":
            from screener import scheduler
            scheduler.start()
```

**Important:** Set `RUN_SCHEDULER=false` when running management commands or tests to prevent the scheduler from starting. Add this to `.env` as `RUN_SCHEDULER=true` for the web service.

### Step 5: Write scheduler test

Basic test: verify jobs are registered but don't actually run them.

### Step 6: Commit

```bash
git add screener/management/commands/run_fundamentals_pipeline.py \
    screener/management/commands/run_options_pipeline.py \
    screener/scheduler.py screener/apps.py \
    screener/tests/test_scheduler.py
git commit -m "feat: pipeline orchestration commands + APScheduler weekly cron"
```

---

## Task 9: Candidates UI

**Goal:** A single Django view showing top CSP candidates, grouped by ticker, with a refresh button that pulls live data.

**Files:**
- Create: `screener/templates/screener/candidates.html`
- Create: `screener/templates/screener/base.html`
- Create: `screener/static/screener/style.css`
- Modify: `screener/views.py`
- Modify: `thetagoblin/urls.py`
- Create: `screener/tests/test_views.py`

### Step 1: Write view tests

```python
class CandidatesViewTest(TestCase):
    def setUp(self):
        # Create a symbol with fundamentals, an options snapshot, seed FilterConfig
        ...

    def test_candidates_page_loads(self):
        resp = self.client.get("/candidates/")
        self.assertEqual(resp.status_code, 200)

    def test_candidates_shows_qualifying_symbols(self):
        resp = self.client.get("/candidates/")
        self.assertContains(resp, "AAPL")

    def test_candidates_excludes_non_qualifying(self):
        # Symbol with low market cap should not appear
        resp = self.client.get("/candidates/")
        self.assertNotContains(resp, "PENNY")

    def test_refresh_triggers_data_pull(self):
        resp = self.client.post("/candidates/refresh/")
        self.assertEqual(resp.status_code, 302)  # redirect back
```

### Step 2: Implement views

```python
# screener/views.py
from django.shortcuts import render, redirect
from screener.services.candidates import get_qualifying_symbols
from screener.models import OptionsSnapshot, FilterConfig


def candidates_view(request):
    cfg = {fc.key: fc.typed_value for fc in FilterConfig.objects.all()}
    symbols = get_qualifying_symbols()

    candidates = []
    for sym in symbols:
        snapshots = OptionsSnapshot.objects.filter(
            symbol=sym,
            delta__isnull=False,
        ).filter(
            delta__lte=-cfg["delta_target_min"],
            delta__gte=-cfg["delta_target_max"],
        ).order_by("expiry_date", "strike")

        if snapshots.exists():
            spot = snapshots.first().spot_price
            options_data = []
            for snap in snapshots:
                otm_pct = (float(spot) - float(snap.strike)) / float(spot) * 100
                options_data.append({
                    "expiry": snap.expiry_date,
                    "dte": snap.dte_at_snapshot,
                    "strike": snap.strike,
                    "otm_pct": round(otm_pct, 1),
                    "bid": snap.bid,
                    "ask": snap.ask,
                    "delta": round(snap.delta, 3),
                    "iv": round(snap.implied_volatility * 100, 1) if snap.implied_volatility else None,
                })
            candidates.append({
                "symbol": sym,
                "spot": spot,
                "options": options_data,
            })

    return render(request, "screener/candidates.html", {
        "candidates": candidates,
        "last_updated": OptionsSnapshot.objects.order_by("-snapshot_date").first(),
    })


def refresh_candidates(request):
    """POST endpoint: re-pull options for displayed candidates."""
    if request.method == "POST":
        from django.core.management import call_command
        call_command("pull_options", limit=50)
    return redirect("candidates")
```

### Step 3: Create templates

**`base.html`:** Minimal HTML5 boilerplate. Use a simple CSS framework — either Pico CSS (classless, ~10KB) or MVP.css for zero-config professional look. Load via CDN. No npm/node build system.

**`candidates.html`:** Extends base. Shows:
- Header: "ThetaGoblin — CSP Candidates" + last updated timestamp
- Refresh button (POST form to `/candidates/refresh/`)
- For each candidate:
  - Card/section: **{TICKER}** — {Name} | Spot: ${spot}
  - Table: Expiry | DTE | Strike | OTM% | Bid | Ask | Delta | IV
  - Rows for each option in the snapshots

### Step 4: Wire URLs

```python
# thetagoblin/urls.py
from screener.views import candidates_view, refresh_candidates

urlpatterns = [
    path("admin/", admin.site.urls),
    path("candidates/", candidates_view, name="candidates"),
    path("candidates/refresh/", refresh_candidates, name="refresh_candidates"),
    path("", RedirectView.as_view(url="/candidates/", permanent=False)),
]
```

### Step 5: Run tests, visually inspect

```bash
docker compose exec web python manage.py test screener.tests.test_views -v2
```

Then open `http://localhost:8000/candidates/` in browser.

### Step 6: Commit

```bash
git add screener/templates/ screener/static/ screener/views.py \
    thetagoblin/urls.py screener/tests/test_views.py
git commit -m "feat: candidates UI with grouped options display + refresh"
```

---

## Task 10: Django Admin Configuration

**Goal:** Custom admin for FilterConfig with inline descriptions and editable values. Basic admin registration for other models.

**Files:**
- Modify: `screener/admin.py`
- Create: `screener/tests/test_admin.py`

### Step 1: Write admin tests

```python
class AdminTest(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        self.admin = User.objects.create_superuser("admin", "a@b.com", "pass")
        self.client.login(username="admin", password="pass")

    def test_filterconfig_changelist_loads(self):
        resp = self.client.get("/admin/screener/filterconfig/")
        self.assertEqual(resp.status_code, 200)

    def test_filterconfig_shows_description(self):
        resp = self.client.get("/admin/screener/filterconfig/")
        self.assertContains(resp, "Minimum market cap")

    def test_symbol_changelist_loads(self):
        resp = self.client.get("/admin/screener/symbol/")
        self.assertEqual(resp.status_code, 200)
```

### Step 2: Implement admin configuration

```python
# screener/admin.py
from django.contrib import admin
from screener.models import Symbol, EarningsDate, OptionsSnapshot, IVRank, FilterConfig


@admin.register(FilterConfig)
class FilterConfigAdmin(admin.ModelAdmin):
    list_display = ["key", "value", "value_type", "description", "updated_at"]
    list_editable = ["value"]
    list_display_links = ["key"]
    search_fields = ["key", "description"]
    list_per_page = 50


@admin.register(Symbol)
class SymbolAdmin(admin.ModelAdmin):
    list_display = ["ticker", "name", "exchange_mic", "market_cap",
                    "operating_margin", "fundamentals_updated_at"]
    list_filter = ["exchange_mic"]
    search_fields = ["ticker", "name"]
    readonly_fields = ["fundamentals_updated_at"]


@admin.register(EarningsDate)
class EarningsDateAdmin(admin.ModelAdmin):
    list_display = ["symbol", "report_date", "source", "last_updated"]
    list_filter = ["source"]
    search_fields = ["symbol__ticker"]


@admin.register(OptionsSnapshot)
class OptionsSnapshotAdmin(admin.ModelAdmin):
    list_display = ["symbol", "snapshot_date", "expiry_date", "strike",
                    "spot_price", "delta", "bid", "ask"]
    list_filter = ["snapshot_date", "expiry_date"]
    search_fields = ["symbol__ticker"]


@admin.register(IVRank)
class IVRankAdmin(admin.ModelAdmin):
    list_display = ["symbol", "computed_date", "iv_rank", "iv_percentile",
                    "is_reliable", "weeks_of_history"]
    list_filter = ["is_reliable", "computed_date"]
    search_fields = ["symbol__ticker"]
```

### Step 3: Create superuser (manual step, documented)

```bash
docker compose exec web python manage.py createsuperuser
```

### Step 4: Run tests, verify admin UI

```bash
docker compose exec web python manage.py test screener.tests.test_admin -v2
```

Visit `http://localhost:8000/admin/` and verify FilterConfig list is editable inline with descriptions visible.

### Step 5: Commit

```bash
git add screener/admin.py screener/tests/test_admin.py
git commit -m "feat: Django admin with custom FilterConfig list view"
```

---

## Post-Implementation Verification Checklist

After all 10 tasks, verify end-to-end:

1. `docker compose up --build` — both services start clean
2. `docker compose exec web python manage.py migrate` — all migrations apply
3. FilterConfig has all 16 seed values in admin
4. `python scripts/build_universe.py` — generates CSV with ~50-150 tickers
5. `docker compose exec web python manage.py load_symbols data/universe.csv` — loads symbols
6. `docker compose exec web python manage.py run_fundamentals_pipeline` — updates fundamentals + earnings
7. `docker compose exec web python manage.py run_options_pipeline` — pulls options data
8. `http://localhost:8000/candidates/` — shows candidates with options tables
9. Refresh button works — re-pulls live data
10. `http://localhost:8000/admin/screener/filterconfig/` — editable thresholds
11. `docker compose exec web python manage.py test` — all tests pass

---

## Architecture Notes for Implementer

### Directory Structure (final state)

```
ThetaGoblin/
├── .env                          # NOT committed
├── .gitignore
├── CLAUDE.md
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── manage.py
├── data/
│   └── universe.csv              # Generated, gitignored
├── scripts/
│   └── build_universe.py         # Standalone Finnhub script
├── thetagoblin/
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── screener/
│   ├── __init__.py
│   ├── apps.py
│   ├── models.py
│   ├── admin.py
│   ├── views.py
│   ├── scheduler.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── finnhub_client.py
│   │   ├── yfinance_svc.py
│   │   ├── options_math.py
│   │   └── candidates.py
│   ├── management/
│   │   ├── __init__.py
│   │   └── commands/
│   │       ├── __init__.py
│   │       ├── load_symbols.py
│   │       ├── pull_fundamentals.py
│   │       ├── pull_earnings.py
│   │       ├── pull_options.py
│   │       ├── run_fundamentals_pipeline.py
│   │       └── run_options_pipeline.py
│   ├── templates/
│   │   └── screener/
│   │       ├── base.html
│   │       └── candidates.html
│   ├── static/
│   │   └── screener/
│   │       └── style.css
│   └── tests/
│       ├── __init__.py
│       ├── test_models.py
│       ├── test_seed.py
│       ├── test_load_symbols.py
│       ├── test_finnhub_client.py
│       ├── test_pull_fundamentals.py
│       ├── test_pull_earnings.py
│       ├── test_options_math.py
│       ├── test_yfinance_svc.py
│       ├── test_pull_options.py
│       ├── test_views.py
│       ├── test_admin.py
│       └── test_scheduler.py
└── docs/
    └── plans/
        └── 2026-02-23-thetagoblin-mvp.md
```

### Key Design Decisions

1. **Candidates are query results, not persisted.** No candidates/legs table. The candidates view runs the filter query live against Symbol + OptionsSnapshot.

2. **Resume logic via timestamps.** `pull_fundamentals` skips symbols updated within `--stale-days`. `pull_options` uses `update_or_create` on (symbol, snapshot_date, expiry_date, strike) — re-running overwrites today's data cleanly.

3. **Delta storage band (0.10–0.35) wider than display band (0.15–0.30).** Changing the display filter in FilterConfig doesn't require re-fetching options data.

4. **APScheduler in-process.** No broker, no extra service. `RUN_SCHEDULER` env var prevents it from starting during management commands/tests.

5. **Finnhub rate limiting:** 1-second delay between calls. Free tier allows 60/min. All calls wrapped in try/except — failures skip the symbol and continue.

6. **risk_free_rate in FilterConfig.** Updatable via admin without code changes. Default 0.043 (current 3-month T-bill as of Feb 2026).
