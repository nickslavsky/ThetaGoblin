import logging
import time
from typing import Callable, TypeVar

from django.conf import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


def call_with_backoff(
    fn: Callable[..., T],
    *args,
    label: str = "",
    retryable_exc: type[Exception] | tuple[type[Exception], ...] = Exception,
    **kwargs,
) -> T:
    """Call *fn* with exponential backoff on transient errors.

    On success, returns whatever *fn* returns.
    After exhausting retries, returns None.

    Args:
        fn: Callable to invoke.
        label: Human-readable label for log messages.
        retryable_exc: Exception type(s) that trigger a retry.
                       Defaults to Exception (retry on any error).

    Backoff parameters are read from Django settings (sourced from .env):
        BACKOFF_BASE         – initial wait in seconds  (default 5)
        BACKOFF_MULTIPLIER   – multiplier per retry     (default 3)
        BACKOFF_MAX          – ceiling in seconds       (default 3600)
        BACKOFF_MAX_RETRIES  – max attempts             (default 10)
    """
    max_retries = settings.BACKOFF_MAX_RETRIES

    for attempt in range(max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except retryable_exc:
            if attempt == max_retries:
                logger.error(
                    "Failed on %s after %d retries, giving up",
                    label, max_retries,
                )
                return None
            wait = min(
                settings.BACKOFF_BASE * (settings.BACKOFF_MULTIPLIER ** attempt),
                settings.BACKOFF_MAX,
            )
            logger.warning(
                "Transient error on %s (attempt %d/%d), backing off %ds",
                label, attempt + 1, max_retries, int(wait),
            )
            time.sleep(wait)
    return None
