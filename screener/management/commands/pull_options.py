import logging
import time
from datetime import date

from django.core.management.base import BaseCommand

from screener.models import FilterConfig, IV30Snapshot, OptionsSnapshot
from screener.services import yfinance_svc
from screener.services.candidates import get_qualifying_symbols
from screener.services.options_math import compute_put_delta

logger = logging.getLogger(__name__)

# Storage band wider than display band — tightening FilterConfig delta thresholds
# does not require re-fetching options data.
DELTA_STORE_MIN = 0.10
DELTA_STORE_MAX = 0.35


class Command(BaseCommand):
    help = "Pull options snapshots for all qualifying symbols"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0,
                            help="Max symbols to process, 0=all (default: 0)")
        parser.add_argument("--delay", type=float, default=0.5,
                            help="Seconds between yfinance chain fetches (default: 0.5)")

    def handle(self, *args, **options):
        limit = options["limit"]
        delay = options["delay"]

        cfg = {fc.key: fc.typed_value for fc in FilterConfig.objects.all()}
        dte_min = cfg["expiry_dte_min"]
        dte_max = cfg["expiry_dte_max"]
        rate = cfg["risk_free_rate"]
        today = date.today()

        symbols = get_qualifying_symbols()
        if limit:
            symbols = symbols[:limit]

        self.stdout.write(f"Processing {len(symbols)} qualifying symbols...")
        total_saved = 0
        skipped_symbols = 0

        for sym in symbols:
            expiries = yfinance_svc.get_expiry_dates(sym.ticker)
            if not expiries:
                skipped_symbols += 1
                continue

            ticker_info = {}
            for expiry_str in expiries:
                try:
                    expiry = date.fromisoformat(expiry_str)
                except ValueError:
                    continue

                dte = (expiry - today).days
                if dte < dte_min or dte > dte_max:
                    continue

                puts = yfinance_svc.get_puts_chain(sym.ticker, expiry_str, ticker_info=ticker_info)
                if puts is None:
                    continue

                for put in puts:
                    vol = put.get("implied_volatility") or 0
                    spot = put.get("spot_price")
                    strike = put.get("strike")

                    if not spot or not vol or not strike:
                        continue

                    delta = compute_put_delta(
                        spot=float(spot), strike=float(strike),
                        dte=dte, vol=vol, rate=rate,
                    )

                    if abs(delta) < DELTA_STORE_MIN or abs(delta) > DELTA_STORE_MAX:
                        continue

                    bid = put.get("bid") or 0
                    ask = put.get("ask") or 0
                    spread_pct = (ask - bid) / bid if bid > 0 else None

                    OptionsSnapshot.objects.update_or_create(
                        symbol=sym,
                        snapshot_date=today,
                        expiry_date=expiry,
                        strike=strike,
                        defaults={
                            "dte_at_snapshot": dte,
                            "spot_price": spot,
                            "implied_volatility": vol,
                            "bid": bid,
                            "ask": ask,
                            "spread_pct": spread_pct,
                            "open_interest": put.get("open_interest") or 0,
                            "volume": put.get("volume") or 0,
                            "delta": delta,
                        },
                    )
                    total_saved += 1

                if delay > 0:
                    time.sleep(delay)

            # Store IV30 snapshot (one per symbol per run)
            iv30_val = ticker_info.get("iv30")
            if iv30_val is not None:
                IV30Snapshot.objects.update_or_create(
                    symbol=sym, date=today,
                    defaults={"iv30": iv30_val},
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Saved {total_saved} snapshots. Skipped {skipped_symbols} symbols."
            )
        )
