from datetime import date

RELIABLE_DAYS = 364  # ~52 weeks


def compute_iv_rank(
    current_iv30: float,
    min_iv30: float,
    max_iv30: float,
    count_lte: int,
    total_count: int,
    earliest_date: date,
    latest_date: date,
) -> dict | None:
    """Compute IV rank and percentile from pre-computed aggregates.

    Returns dict with iv_rank, iv_percentile, weeks_of_history, is_reliable,
    or None if <2 data points or max == min.
    """
    if total_count < 2 or max_iv30 == min_iv30:
        return None

    span_days = (latest_date - earliest_date).days
    return {
        "iv_rank": (current_iv30 - min_iv30) / (max_iv30 - min_iv30) * 100,
        "iv_percentile": count_lte / total_count * 100,
        "weeks_of_history": span_days // 7,
        "is_reliable": span_days >= RELIABLE_DAYS,
    }
