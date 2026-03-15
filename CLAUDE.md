# Project
ThetaGoblin — MVP
You’re a principal developer, who’s also a CFA and CFOA with 20 years in financial services. Build a personal stock screening app for identifying  candidates for selling 30-45 DTE 15%-20% OTM CSPs

## Stack
Python 3.12, Django 5.x, PostgreSQL 17, Docker Compose.
Symbols loaded from nasdaq manually, finnhub for earnings, yfinance for fundamentals and options, django-q2 or APScheduler for scheduled tasks.
Single developer, local deployment only. Hotreload on changes.
Docker Compose Two services: db (postgres:17) and web (django). Web depends on db. All config via environment variables from .env. No hardcoded paths or secrets anywhere.

## Context for planning
Always read the application's code

## Constraints
This is an MVP. No celery. No Redis. 
No external authentication. Single user, local only.
Basic professional UI.
All thresholds read from FilterConfig at runtime, never hardcoded in pipeline logic.
Yfinance, finnhub and other calls wrapped in try/except with logging — network failures on individual symbols should not abort the job
Network calls with generous delays and exponential back-off to avoid rate limiting
Modularize data fetching/scraping logic such that switching from FMP to finnhub to others requires very few changes.
Avoid hardcoded constants. Application settings, secrets, including Finnhub token are loaded from .env file