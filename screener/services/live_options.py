import logging
from datetime import date

from screener.services import yfinance_svc
from screener.services.options_math import compute_put_delta

logger = logging.getLogger(__name__)


def fetch_live_options(symbols, cfg: dict) -> list[dict]:
    """Fetch live options data for display only — no DB writes.

    Returns list of candidate dicts with the same shape as candidates_view builds,
    so the same template works for both DB-backed and live data.
    """
    dte_min = cfg.get("expiry_dte_min", 30)
    dte_max = cfg.get("expiry_dte_max", 45)
    rate = cfg.get("risk_free_rate", 0.043)
    delta_min = cfg.get("delta_target_min", 0.15)
    delta_max = cfg.get("delta_target_max", 0.30)
    otm_min = cfg.get("otm_pct_min", 0.15)
    otm_max = cfg.get("otm_pct_max", 0.20)

    today = date.today()
    candidates = []

    for sym in symbols:
        try:
            expiries = yfinance_svc.get_expiry_dates(sym.ticker)
        except Exception:
            logger.exception("Failed to get expiries for %s", sym.ticker)
            continue

        if not expiries:
            continue

        options_data = []
        spot = None

        for expiry_str in expiries:
            try:
                expiry = date.fromisoformat(expiry_str)
            except ValueError:
                continue

            dte = (expiry - today).days
            if dte < dte_min or dte > dte_max:
                continue

            puts = yfinance_svc.get_puts_chain(sym.ticker, expiry_str)
            if puts is None:
                continue

            for put in puts:
                vol = put.get("implied_volatility") or 0
                put_spot = put.get("spot_price")
                strike = put.get("strike")

                if not put_spot or not vol or not strike:
                    continue

                if spot is None:
                    spot = put_spot

                delta = compute_put_delta(
                    spot=float(put_spot), strike=float(strike),
                    dte=dte, vol=vol, rate=rate,
                )

                if abs(delta) < delta_min or abs(delta) > delta_max:
                    continue

                otm_pct = (float(put_spot) - float(strike)) / float(put_spot) * 100
                if not (otm_min * 100 <= otm_pct <= otm_max * 100):
                    continue

                options_data.append({
                    "expiry": expiry,
                    "dte": dte,
                    "strike": strike,
                    "otm_pct": round(otm_pct, 1),
                    "bid": put.get("bid"),
                    "ask": put.get("ask"),
                    "delta": round(delta, 3),
                    "iv": round(vol * 100, 1) if vol else None,
                })

        if options_data and spot is not None:
            candidates.append({
                "symbol": sym,
                "spot": spot,
                "options": options_data,
            })

    return candidates
