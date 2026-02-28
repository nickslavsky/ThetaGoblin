import math
from scipy.stats import norm


def compute_atm_iv(puts: list[dict], spot: float) -> float | None:
    """Derive ATM implied volatility from a puts chain.

    Finds the two strikes bracketing spot (highest ≤ spot, lowest > spot)
    and returns their average IV.  Falls back to a single side if spot is
    outside the strike range.  Returns None when no usable IV exists.
    """
    valid = [(p["strike"], p["implied_volatility"])
             for p in puts
             if p.get("implied_volatility") and p.get("strike")]
    if not valid:
        return None

    below = [(s, iv) for s, iv in valid if s <= spot]
    above = [(s, iv) for s, iv in valid if s > spot]

    bracket_iv: list[float] = []
    if below:
        bracket_iv.append(max(below, key=lambda x: x[0])[1])
    if above:
        bracket_iv.append(min(above, key=lambda x: x[0])[1])

    return sum(bracket_iv) / len(bracket_iv) if bracket_iv else None


def select_iv30_from_expiries(expiry_ivs: list[tuple[int, float]]) -> float | None:
    """Pick the ATM IV from the expiry closest to 30 DTE.

    Takes a list of (dte, atm_iv) tuples and returns the atm_iv whose
    dte is nearest to 30.  Returns None for an empty list.
    """
    if not expiry_ivs:
        return None
    return min(expiry_ivs, key=lambda x: abs(x[0] - 30))[1]


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
