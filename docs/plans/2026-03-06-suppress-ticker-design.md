# Suppress Ticker Until Expiry

## Problem

After selling a CSP on a ticker, ThetaGoblin continues showing it as a candidate.
The user needs a one-click way to suppress a ticker until the sold option expires.

## Design

### Data Model

- Add nullable `suppress_until` (DateField, null=True, blank=True) to `Symbol`
- Visible and editable in Django admin for manual corrections

### Candidates Pipeline (services/candidates.py)

- Add filter to `get_qualifying_symbols()`: exclude symbols where `suppress_until >= today`
- Symbols with `suppress_until IS NULL` or `suppress_until < today` pass through
- Strict inequality: the option must be expired or rolled before the ticker reappears

### API Endpoint

- `POST /candidates/suppress/` accepting `symbol_id` and `suppress_until` (date string)
- Sets the field on Symbol, returns 200 JSON
- View function in `views.py`, URL entry in `urls.py`

### Frontend (candidates.html)

- Expiry date cells get CSS hover highlight (cursor pointer, background change)
- On click: `fetch()` POST to suppress endpoint, on success remove entire ticker section from DOM
- No confirmation dialog, no undo, no toast

### What doesn't change

- All data pipelines (fundamentals, earnings, options, IV) continue as-is
- FilterConfig not involved — per-symbol state, not a threshold
- Admin gets the field for free via existing Symbol registration
