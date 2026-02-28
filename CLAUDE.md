# Project
ThetaGoblin — MVP
You’re a principal developer, who’s also a CFA and CFOA with 20 years in financial services. Build a personal stock screening app for identifying CSP (cash-secured put) candidates. 

## Stack
Python 3.12, Django 5.x, PostgreSQL 17, Docker Compose, finnhub for symbols and fundamentals, yfinance for options, django-q2 or APScheduler for scheduled tasks.
Single developer, local deployment only. Hotreload on changes.
Docker Compose Two services: db (postgres:17) and web (django). Web depends on db. All config via environment variables from .env. No hardcoded paths or secrets anywhere.

## Context for planning
Pull datamodel from migrations and models in the application

#### FilterConfig default seeds
market_cap_min	10000000000
operating_margin_min	0.0
free_cash_flow_min	0
debt_to_equity_max	2.0
earnings_exclusion_days	50
iv_rank_min	70
iv_rank_max	90
iv_min	0.20
iv_max	0.40
delta_target_min	0.15
delta_target_max	0.30
otm_pct_target	0.175
expiry_dte_min	30
expiry_dte_max	45
risk_free_rate	0.043
otm_pct_min	0.15
otm_pct_max	0.20
min_avg_volume	1.5
min_notional_oi	1500

### Scheduled background jobs

- Refresh fundamentals 
- Weekly on Friday after markets close: Pull options snapshot, update IV ranking (yfinance)
- Weekly update earnings. Can also do it on Friday to capture last week’s data?
https://finnhub.io/api/v1/calendar/earnings?from=2026-02-23&to=2026-03-07&token=

### Options logic
For each qualifying ticker
Get all available expiries from ticker.options
Filter to those where DTE is between expiry_dte_min and expiry_dte_max
For each qualifying expiry, fetch the puts chain
Compute delta for each strike, keep rows where abs(delta) is between 0.10 and 0.35
Store each as its own row in options_snapshot

### Identifying candidates
Load symbols from DB that satisfy fundamentals filter
market_cap > 10B AND operating_margin > 0 AND cash_flow_per_share_annual > 0 AND ten_day_avg_trading_volume > 10M AND long_term_debt_to_equity_annual < 2 and don’t have earning in the next earnings_exclusion_days
Apply IV rank filter (use raw iv_30 if rank unreliable, flag candidates accordingly)
List top candidates, for each list prices for strikes 15-20% OTM in the target expiries
We call yfinance again with the top candidates to update deltas when we render the  UI - this is done live, without storing options in the database. This is a precursor to live updates in the future.

### Initial data load for MVP
A way to import tickers, fundamentals with a script.
Need two mgmt commands:
- Run fundamentals job. Need logic to start where the previous job failed/left off so it doesn’t churn the same tickers over and over failing after 100 symbols if rate limited. 
- Run the options job. Same logic to pick up where the previous run left off
UI — one Django app
Candidates view: section for each ticket with its spot. Inside the section a small table: expiry dates, strike, OTM % bid, ask, delta. For the MVP - refresh button that reloads all top candidates, their latest spot and options data.
FilterConfig gets a custom admin view with descriptions visible inline. 

### What to build first — in this order
Docker Compose with hot reload + Django project scaffold + .env wiring
Models + migrations
FilterConfig seed data migration
Script to load symbols and fundamentals from a small CSV
Fundamentals pull/refresh job 
Earnings calendar pull
Options data pull and calc job
Pipeline orchestration (two mgmt jobs)
UI with candidates
Django admin configuration

### Constraints
This is an MVP. No celery. No Redis. 
No external authentication. Single user, local only.
Basic professional UI, not plain HTML
All thresholds read from FilterConfig at runtime, never hardcoded in pipeline logic.
Yfinance, finnhub and other calls wrapped in try/except with logging — network failures on individual symbols should not abort the job
Network calls with generous delays and exponential back-off to avoid rate limiting
Modularize data fetching/scraping logic such that switching from FMP to finnhub to others requires very few changes.
Avoid hardcoded constants. Application settings, secrets, including Finnhub token are loaded from .env file as `FINNHUB_TOKEN`