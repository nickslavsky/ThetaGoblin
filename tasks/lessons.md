# Lessons Learned

## Finnhub Earnings Calendar API — 1500 Record Limit

**Discovered:** 2026-02-26

**Problem:** The Finnhub `/calendar/earnings` endpoint returns a maximum of ~1500 entries per request, ordered descending from the `to` date. When querying a wide date range (e.g., 8 weeks), the response silently truncates — earlier dates in the range are missing with no indication of truncation in the response.

**How to detect:** Run the pull job for a given date range, then check the `EarningsDate` table. The earliest `report_date` won't match the `from` date passed to the API — there's a gap at the beginning of the range.

**Impact:** The `pull_earnings` command with `--weeks-ahead=8` misses earnings dates in the earlier portion of the window, causing the candidate pipeline to incorrectly include symbols that actually have upcoming earnings.

**Rule:** Always assume paginated/limited API responses. When an API returns a round-ish number of results close to a known limit, treat it as truncated. Chunk large date ranges into smaller windows that fit within API limits.

## Rate Limit Padding — Never Use the Theoretical Minimum

**Discovered:** 2026-02-27

**Problem:** When an API allows N requests per T seconds (e.g., Finnhub: 30 req/30s), setting delay to exactly T/N (1.0s) is insufficient. Two requests sent 1s apart from the client can arrive with <1s interval at the server due to network jitter, variable processing time, TCP batching, and clock differences. This causes 429 errors that cascade — once rate-limited, every subsequent request also fails.

**Rule:** Always pad the inter-request delay beyond the theoretical minimum. For a 1 req/s limit, use 1.1–1.2s. For tighter limits, pad proportionally more. The cost of slightly slower throughput is negligible compared to cascading 429 failures.

## Exponential Backoff on Rate Limits — Build for Unattended Operation

**Discovered:** 2026-02-27

**Problem:** On 429 errors, the fundamentals pull skipped the symbol with the same 1s delay and moved to the next — which also got 429'd. The job burned through the entire queue failing every request, then stopped. If this happens on Friday evening, the job sits idle all weekend.

**Rule:** On rate limit (429): retry the SAME request with exponential backoff (not skip to next). Use generous caps (e.g., base 5s, multiplier 3x, max 60min, many retries). For batch jobs meant to run unattended, prefer "too patient" over "gives up too early." A job that takes 48 hours is fine; a job that fails in 5 minutes and sits idle is not.
