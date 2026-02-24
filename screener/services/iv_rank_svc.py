RELIABLE_WEEKS = 52


def compute_iv_rank(current_iv30: float, historical_iv30s: list[float]) -> dict | None:
    """Compute IV rank and percentile from historical IV30 data.

    Returns dict with iv_rank, iv_percentile, weeks_of_history, is_reliable,
    or None if <2 data points or max == min.
    """
    if len(historical_iv30s) < 2:
        return None

    lo = min(historical_iv30s)
    hi = max(historical_iv30s)
    if hi == lo:
        return None

    iv_rank = (current_iv30 - lo) / (hi - lo) * 100
    count_lte = sum(1 for v in historical_iv30s if v <= current_iv30)
    iv_percentile = count_lte / len(historical_iv30s) * 100

    return {
        "iv_rank": iv_rank,
        "iv_percentile": iv_percentile,
        "weeks_of_history": len(historical_iv30s),
        "is_reliable": len(historical_iv30s) >= RELIABLE_WEEKS,
    }
