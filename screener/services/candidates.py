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
    )

    today = date.today()
    exclusion_cutoff = today + timedelta(days=cfg["earnings_exclusion_days"])
    tickers_with_upcoming_earnings = EarningsDate.objects.filter(
        report_date__gte=today,
        report_date__lte=exclusion_cutoff,
    ).values_list("symbol__ticker", flat=True)

    symbols = symbols.exclude(ticker__in=tickers_with_upcoming_earnings)
    return list(symbols)
