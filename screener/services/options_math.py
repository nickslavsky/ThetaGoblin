import math
from scipy.stats import norm


def compute_put_delta(spot: float, strike: float, dte: int,
                      vol: float, rate: float) -> float:
    """Black-Scholes put delta. Returns value between -1.0 and 0.0.
    Returns 0.0 for degenerate inputs (dte=0, vol=0, spot=0, strike=0).
    """
    if dte <= 0 or vol <= 0 or spot <= 0 or strike <= 0:
        return 0.0
    T = dte / 365.0
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol ** 2) * T) / (vol * math.sqrt(T))
    return float(norm.cdf(d1) - 1.0)
