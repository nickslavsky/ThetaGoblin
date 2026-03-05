import logging
from datetime import date

from django.shortcuts import redirect, render

from screener.models import FilterConfig, IVRank, OptionsSnapshot
from screener.services.candidates import get_qualifying_symbols
from screener.services.live_options import fetch_live_options

logger = logging.getLogger(__name__)


def candidates_view(request):
    cfg = {fc.key: fc.typed_value for fc in FilterConfig.objects.all()}
    delta_min = cfg.get("delta_target_min", 0.15)
    delta_max = cfg.get("delta_target_max", 0.30)
    otm_min = cfg.get("otm_pct_min", 0.15)
    otm_max = cfg.get("otm_pct_max", 0.20)
    min_notional_oi = cfg.get("min_notional_oi", 10_000_000)

    qualifying_symbols = get_qualifying_symbols()
    logger.debug("View funnel: %d qualifying symbols", len(qualifying_symbols))

    # Bulk fetch IVRank for display
    iv_ranks = {
        r.symbol_id: r
        for r in IVRank.objects.filter(symbol__in=qualifying_symbols)
    }

    candidates = []
    filtered_no_snapshots = 0
    filtered_no_otm_match = 0
    filtered_low_notional_oi = 0
    for sym in qualifying_symbols:
        rank_obj = iv_ranks.get(sym.pk)

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
            filtered_no_snapshots += 1
            continue

        spot = snapshots.first().spot_price
        options_data = []
        oi_strike_pairs = []
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
            oi_strike_pairs.append((snap.open_interest or 0, float(snap.strike)))

        if not options_data:
            filtered_no_otm_match += 1
            continue

        # Compute notional OI: avg(open_interest) x avg(strike) across qualifying strikes
        avg_oi = sum(oi for oi, _ in oi_strike_pairs) / len(oi_strike_pairs)
        avg_strike = sum(s for _, s in oi_strike_pairs) / len(oi_strike_pairs)
        notional_oi = avg_oi * avg_strike

        if notional_oi < min_notional_oi:
            filtered_low_notional_oi += 1
            continue

        # Build IV rank display info
        iv_rank_display = None
        iv_rank_reliable = None
        if rank_obj:
            iv_rank_display = round(rank_obj.iv_rank, 1)
            iv_rank_reliable = rank_obj.is_reliable

        candidates.append(
            {
                "symbol": sym,
                "spot": spot,
                "options": options_data,
                "iv_rank": iv_rank_display,
                "iv_rank_reliable": iv_rank_reliable,
                "notional_oi": f"${notional_oi:,.0f}",
            }
        )

    logger.debug(
        "View funnel: %d no option snapshots in delta range, "
        "%d no strikes in OTM range (%s%%-%s%%), %d low notional OI (<%s) → %d final candidates",
        filtered_no_snapshots,
        filtered_no_otm_match, otm_min * 100, otm_max * 100,
        filtered_low_notional_oi, f"${min_notional_oi:,.0f}",
        len(candidates),
    )

    last_snapshot = OptionsSnapshot.objects.order_by("-snapshot_date").first()

    return render(
        request,
        "screener/candidates.html",
        {
            "candidates": candidates,
            "last_snapshot": last_snapshot,
            "candidate_count": len(candidates),
            "is_live": False,
        },
    )


def refresh_candidates(request):
    """Fetch live options for display only — no DB writes."""
    cfg = {fc.key: fc.typed_value for fc in FilterConfig.objects.all()}
    qualifying_symbols = get_qualifying_symbols()

    try:
        candidates = fetch_live_options(qualifying_symbols, cfg)
    except Exception:
        logger.exception("Refresh failed")
        candidates = []

    return render(
        request,
        "screener/candidates.html",
        {
            "candidates": candidates,
            "candidate_count": len(candidates),
            "is_live": True,
        },
    )
