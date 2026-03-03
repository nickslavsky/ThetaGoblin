# Project
ThetaGoblin — MVP
You’re a principal developer, who’s also a CFA and CFOA with 20 years in financial services. Build a personal stock screening app for identifying CSP (cash-secured put) candidates. 

## Stack
Python 3.12, Django 5.x, PostgreSQL 17, Docker Compose, finnhub for symbols and fundamentals, yfinance for options, django-q2 or APScheduler for scheduled tasks.
Single developer, local deployment only. Hotreload on changes.
Docker Compose Two services: db (postgres:17) and web (django). Web depends on db. All config via environment variables from .env. No hardcoded paths or secrets anywhere.

## Context for planning
Pull datamodel from migrations and models in the application


### Scheduled background jobs

- Refresh fundamentals 
- refresh options snapshot
- refresh IV data, update iv ranks
- update earnings


### Constraints
This is an MVP. No celery. No Redis. 
No external authentication. Single user, local only.
Basic professional UI, not plain HTML
All thresholds read from FilterConfig at runtime, never hardcoded in pipeline logic.
Yfinance, finnhub and other calls wrapped in try/except with logging — network failures on individual symbols should not abort the job
Network calls with generous delays and exponential back-off to avoid rate limiting
Modularize data fetching/scraping logic such that switching from FMP to finnhub to others requires very few changes.
Avoid hardcoded constants. Application settings, secrets, including Finnhub token are loaded from .env file as `FINNHUB_TOKEN`