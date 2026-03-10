import logging
from datetime import date, timedelta

from screener.models import EarningsDate, FilterConfig, Symbol

logger = logging.getLogger(__name__)


def get_qualifying_symbols() -> list:
    """Return symbols passing all fundamental + earnings exclusion filters.
    All thresholds read from FilterConfig at runtime.
    """
    cfg = {fc.key: fc.typed_value for fc in FilterConfig.objects.all()}

    symbols = Symbol.objects.filter(
        market_cap__isnull=False,
        market_cap__gte=cfg["market_cap_min"],
        operating_margin__gt=cfg["operating_margin_min"],
        cash_flow_per_share_annual__gt=cfg["free_cash_flow_min"],
        long_term_debt_to_equity_annual__lt=cfg["debt_to_equity_max"],
        ten_day_avg_trading_volume__gte=cfg["min_avg_volume"],
    )

    today = date.today()

    # Suppress filter: hide symbols with active suppress_until
    symbols = symbols.exclude(suppress_until__gte=today)

    exclusion_cutoff = today + timedelta(days=cfg["earnings_exclusion_days"])
    logger.debug("Earnings exclusion window: %s to %s", today, exclusion_cutoff)
    tickers_with_upcoming_earnings = set(
        EarningsDate.objects.filter(
            report_date__gte=today,
            report_date__lte=exclusion_cutoff,
        ).values_list("symbol__ticker", flat=True)
    )

    symbols = symbols.exclude(ticker__in=tickers_with_upcoming_earnings)

    # IV rank filter: require reliable IV rank within [min, max]
    symbols = symbols.filter(
        iv_ranks__is_reliable=True,
        iv_ranks__iv_rank__gte=cfg["iv_rank_min"],
        iv_ranks__iv_rank__lte=cfg["iv_rank_max"],
    )

    result = list(symbols)
    logger.info("Candidates pipeline: %d symbols qualify after all filters", len(result))
    return result
