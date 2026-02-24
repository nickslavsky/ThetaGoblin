import logging
from datetime import date

from django.core.management import call_command
from django.shortcuts import redirect, render

from screener.models import FilterConfig, OptionsSnapshot
from screener.services.candidates import get_qualifying_symbols

logger = logging.getLogger(__name__)


def candidates_view(request):
    cfg = {fc.key: fc.typed_value for fc in FilterConfig.objects.all()}
    delta_min = cfg.get("delta_target_min", 0.15)
    delta_max = cfg.get("delta_target_max", 0.30)
    otm_min = cfg.get("otm_pct_min", 0.15)
    otm_max = cfg.get("otm_pct_max", 0.20)

    qualifying_symbols = get_qualifying_symbols()

    candidates = []
    for sym in qualifying_symbols:
        snapshots = (
            OptionsSnapshot.objects.filter(
                symbol=sym,
                delta__isnull=False,
                delta__lte=-delta_min,
                delta__gte=-delta_max,
            )
            .order_by("expiry_date", "strike")
        )

        if not snapshots.exists():
            continue

        spot = snapshots.first().spot_price
        options_data = []
        for snap in snapshots:
            otm_pct = (float(spot) - float(snap.strike)) / float(spot) * 100
            if not (otm_min * 100 <= otm_pct <= otm_max * 100):
                continue
            options_data.append(
                {
                    "expiry": snap.expiry_date,
                    "dte": snap.dte_at_snapshot,
                    "strike": snap.strike,
                    "otm_pct": round(otm_pct, 1),
                    "bid": snap.bid,
                    "ask": snap.ask,
                    "delta": round(snap.delta, 3),
                    "iv": (
                        round(snap.implied_volatility * 100, 1)
                        if snap.implied_volatility
                        else None
                    ),
                }
            )

        if not options_data:
            continue

        candidates.append(
            {
                "symbol": sym,
                "spot": spot,
                "options": options_data,
            }
        )

    last_snapshot = OptionsSnapshot.objects.order_by("-snapshot_date").first()

    return render(
        request,
        "screener/candidates.html",
        {
            "candidates": candidates,
            "last_snapshot": last_snapshot,
            "candidate_count": len(candidates),
        },
    )


def refresh_candidates(request):
    """Trigger a live options pull for currently qualifying symbols."""
    try:
        call_command("pull_options", limit=50, delay=0.5)
    except Exception:
        logger.exception("Refresh failed")
    return redirect("candidates")
