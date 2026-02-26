import logging
from datetime import date, timedelta

from screener.models import EarningsDate, FilterConfig, Symbol

logger = logging.getLogger(__name__)


def get_qualifying_symbols() -> list:
    """Return symbols passing all fundamental + earnings exclusion filters.
    All thresholds read from FilterConfig at runtime.
    """
    cfg = {fc.key: fc.typed_value for fc in FilterConfig.objects.all()}

    total = Symbol.objects.count()
    logger.debug("Candidates funnel: %d total symbols in universe", total)

    has_market_cap = Symbol.objects.filter(market_cap__isnull=False).count()
    logger.debug("Candidates funnel: %d have market_cap data", has_market_cap)

    symbols = Symbol.objects.filter(
        market_cap__isnull=False,
        market_cap__gte=cfg["market_cap_min"],
    )
    logger.debug("Candidates funnel: %d pass market_cap >= %s", symbols.count(), cfg["market_cap_min"])

    symbols = symbols.filter(operating_margin__gt=cfg["operating_margin_min"])
    logger.debug("Candidates funnel: %d pass operating_margin > %s", symbols.count(), cfg["operating_margin_min"])

    symbols = symbols.filter(cash_flow_per_share_annual__gt=cfg["free_cash_flow_min"])
    logger.debug("Candidates funnel: %d pass cash_flow > %s", symbols.count(), cfg["free_cash_flow_min"])

    symbols = symbols.filter(long_term_debt_to_equity_annual__lt=cfg["debt_to_equity_max"])
    logger.debug("Candidates funnel: %d pass debt_to_equity < %s", symbols.count(), cfg["debt_to_equity_max"])

    today = date.today()
    exclusion_cutoff = today + timedelta(days=cfg["earnings_exclusion_days"])
    tickers_with_upcoming_earnings = set(
        EarningsDate.objects.filter(
            report_date__gte=today,
            report_date__lte=exclusion_cutoff,
        ).values_list("symbol__ticker", flat=True)
    )
    logger.debug(
        "Candidates funnel: %d tickers have earnings within %s days (excluded)",
        len(tickers_with_upcoming_earnings),
        cfg["earnings_exclusion_days"],
    )

    symbols = symbols.exclude(ticker__in=tickers_with_upcoming_earnings)
    result = list(symbols)
    logger.debug("Candidates funnel: %d symbols after earnings exclusion (final)", len(result))
    return result
