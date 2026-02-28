import logging
import time
from typing import Callable, TypeVar

from django.conf import settings

from screener.services.finnhub_client import RateLimitError

logger = logging.getLogger(__name__)

T = TypeVar("T")


def call_with_backoff(fn: Callable[..., T], *args, label: str = "", **kwargs) -> T:
    """Call *fn* with exponential backoff on RateLimitError.

    On success, returns whatever *fn* returns.
    After exhausting retries, returns None.

    Backoff parameters are read from Django settings (sourced from .env):
        FINNHUB_BACKOFF_BASE         – initial wait in seconds  (default 5)
        FINNHUB_BACKOFF_MULTIPLIER   – multiplier per retry     (default 3)
        FINNHUB_BACKOFF_MAX          – ceiling in seconds       (default 3600)
        FINNHUB_BACKOFF_MAX_RETRIES  – max attempts             (default 10)
    """
    max_retries = settings.FINNHUB_BACKOFF_MAX_RETRIES

    for attempt in range(max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except RateLimitError:
            if attempt == max_retries:
                logger.error(
                    "Rate limited on %s after %d retries, giving up",
                    label, max_retries,
                )
                return None
            wait = min(
                settings.FINNHUB_BACKOFF_BASE * (settings.FINNHUB_BACKOFF_MULTIPLIER ** attempt),
                settings.FINNHUB_BACKOFF_MAX,
            )
            logger.warning(
                "Rate limited on %s (attempt %d/%d), backing off %ds",
                label, attempt + 1, max_retries, int(wait),
            )
            time.sleep(wait)
    return None
