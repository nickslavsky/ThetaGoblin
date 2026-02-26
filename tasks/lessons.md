# Lessons Learned

## Finnhub Earnings Calendar API — 1500 Record Limit

**Discovered:** 2026-02-26

**Problem:** The Finnhub `/calendar/earnings` endpoint returns a maximum of ~1500 entries per request, ordered descending from the `to` date. When querying a wide date range (e.g., 8 weeks), the response silently truncates — earlier dates in the range are missing with no indication of truncation in the response.

**How to detect:** Run the pull job for a given date range, then check the `EarningsDate` table. The earliest `report_date` won't match the `from` date passed to the API — there's a gap at the beginning of the range.

**Impact:** The `pull_earnings` command with `--weeks-ahead=8` misses earnings dates in the earlier portion of the window, causing the candidate pipeline to incorrectly include symbols that actually have upcoming earnings.

**Rule:** Always assume paginated/limited API responses. When an API returns a round-ish number of results close to a known limit, treat it as truncated. Chunk large date ranges into smaller windows that fit within API limits.
