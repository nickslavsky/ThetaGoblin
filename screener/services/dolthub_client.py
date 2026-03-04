"""Client for the DoltHub public SQL API (options volatility data).

Provides access to the post-no-preference/options dataset on DoltHub,
which contains historical IV data for US equities.

Uses only stdlib (urllib) -- no requests dependency.
"""

import json
import logging
import re
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

DOLTHUB_API_URL = (
    "https://www.dolthub.com/api/v1alpha1/post-no-preference/options/master"
)
REQUEST_TIMEOUT = 30  # seconds

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class DoltHubError(Exception):
    """Raised on retryable DoltHub API errors (HTTP 429, 5xx)."""

    pass


def _execute_query(sql: str) -> dict:
    """Execute a SQL query against the DoltHub API.

    Returns the parsed JSON response dict on success.
    Raises DoltHubError on HTTP 429 or 5xx (retryable errors).
    Raises OSError / other exceptions on non-retryable network failures.
    """
    encoded_sql = quote(sql)
    url = f"{DOLTHUB_API_URL}?q={encoded_sql}"

    logger.debug("DoltHub SQL: %s", sql)
    logger.debug("DoltHub URL: %s", url)

    req = Request(url, headers={"Accept": "application/json"})

    try:
        with urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            logger.debug("DoltHub response status: %d", resp.status)
            data = json.loads(resp.read().decode())
            return data
    except HTTPError as exc:
        if exc.code == 429 or exc.code >= 500:
            raise DoltHubError(
                f"DoltHub HTTP {exc.code}: {exc.reason}"
            ) from exc
        raise


def fetch_iv_rows(
    date_from: str,
    date_to: str,
    sym_min: str | None = None,
    sym_max: str | None = None,
) -> list[dict]:
    """Fetch IV rows from DoltHub for a date range.

    Args:
        date_from: inclusive start date (YYYY-MM-DD)
        date_to: exclusive end date (YYYY-MM-DD)
        sym_min: optional inclusive lower bound for act_symbol (alphabet batching)
        sym_max: optional exclusive upper bound for act_symbol (alphabet batching)

    Returns list of row dicts on success, [] on any error.
    Raises ValueError on malformed date inputs.
    """
    if not _DATE_RE.match(date_from) or not _DATE_RE.match(date_to):
        raise ValueError(f"Invalid date format: {date_from!r}, {date_to!r}")

    sql = (
        f"SELECT date, act_symbol, iv_current "
        f"FROM volatility_history "
        f"WHERE date >= '{date_from}' AND date < '{date_to}' "
        f"AND iv_current IS NOT NULL"
    )
    if sym_min is not None:
        sql += f" AND act_symbol >= '{sym_min}'"
    if sym_max is not None:
        sql += f" AND act_symbol < '{sym_max}'"
    sql += " ORDER BY act_symbol"

    try:
        data = _execute_query(sql)
        status = data.get("query_execution_status", "")
        if status != "Success":
            logger.warning("DoltHub query returned status: %s", status)
            return []
        rows = data.get("rows", [])
        logger.debug("DoltHub returned %d rows", len(rows))
        return rows
    except DoltHubError:
        raise
    except Exception:
        logger.exception("Failed to fetch IV rows from DoltHub")
        return []


def fetch_latest_date() -> str | None:
    """Fetch the most recent date with IV data from DoltHub.

    Returns date string (YYYY-MM-DD) or None on error.
    """
    sql = (
        "SELECT MAX(date) as latest "
        "FROM volatility_history "
        "WHERE iv_current IS NOT NULL"
    )
    try:
        data = _execute_query(sql)
        status = data.get("query_execution_status", "")
        if status != "Success":
            logger.warning("DoltHub query returned status: %s", status)
            return None
        rows = data.get("rows", [])
        if not rows:
            return None
        latest = rows[0].get("latest")
        logger.debug("DoltHub latest date: %s", latest)
        return latest
    except Exception:
        logger.exception("Failed to fetch latest date from DoltHub")
        return None
