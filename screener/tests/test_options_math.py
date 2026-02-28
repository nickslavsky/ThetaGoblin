from django.test import TestCase
from screener.services.options_math import (
    compute_atm_iv,
    compute_put_delta,
    select_iv30_from_expiries,
)


class BlackScholesDeltaTest(TestCase):

    def test_atm_put_delta_near_minus_half(self):
        delta = compute_put_delta(spot=100.0, strike=100.0, dte=30, vol=0.25, rate=0.043)
        self.assertAlmostEqual(delta, -0.48, places=1)

    def test_deep_otm_put_delta_near_zero(self):
        delta = compute_put_delta(spot=100.0, strike=70.0, dte=30, vol=0.25, rate=0.043)
        self.assertAlmostEqual(delta, 0.0, places=1)

    def test_deep_itm_put_delta_near_minus_one(self):
        delta = compute_put_delta(spot=100.0, strike=130.0, dte=30, vol=0.25, rate=0.043)
        self.assertAlmostEqual(delta, -1.0, places=1)

    def test_zero_dte_returns_zero(self):
        delta = compute_put_delta(spot=100.0, strike=95.0, dte=0, vol=0.25, rate=0.043)
        self.assertEqual(delta, 0.0)

    def test_zero_vol_returns_zero(self):
        delta = compute_put_delta(spot=100.0, strike=95.0, dte=30, vol=0.0, rate=0.043)
        self.assertEqual(delta, 0.0)

    def test_result_is_negative_for_put(self):
        delta = compute_put_delta(spot=100.0, strike=85.0, dte=35, vol=0.30, rate=0.043)
        self.assertLess(delta, 0.0)

    def test_higher_vol_increases_abs_delta_for_otm_put(self):
        low_vol = compute_put_delta(spot=100.0, strike=80.0, dte=35, vol=0.20, rate=0.043)
        high_vol = compute_put_delta(spot=100.0, strike=80.0, dte=35, vol=0.50, rate=0.043)
        # Higher vol increases the magnitude of put delta; numerically high_vol is more negative
        self.assertGreater(abs(high_vol), abs(low_vol))


class ComputeAtmIvTest(TestCase):

    def test_normal_bracket(self):
        """Spot between two strikes → average of bracketing IVs."""
        puts = [
            {"strike": 95.0, "implied_volatility": 0.30},
            {"strike": 105.0, "implied_volatility": 0.26},
        ]
        result = compute_atm_iv(puts, spot=100.0)
        self.assertAlmostEqual(result, 0.28)

    def test_spot_below_all_strikes(self):
        """Spot below all strikes → use lowest strike IV only."""
        puts = [
            {"strike": 105.0, "implied_volatility": 0.26},
            {"strike": 110.0, "implied_volatility": 0.24},
        ]
        result = compute_atm_iv(puts, spot=100.0)
        self.assertAlmostEqual(result, 0.26)

    def test_spot_above_all_strikes(self):
        """Spot above all strikes → use highest strike IV only."""
        puts = [
            {"strike": 90.0, "implied_volatility": 0.32},
            {"strike": 95.0, "implied_volatility": 0.30},
        ]
        result = compute_atm_iv(puts, spot=100.0)
        self.assertAlmostEqual(result, 0.30)

    def test_empty_chain(self):
        result = compute_atm_iv([], spot=100.0)
        self.assertIsNone(result)

    def test_all_zero_iv(self):
        puts = [
            {"strike": 95.0, "implied_volatility": 0.0},
            {"strike": 105.0, "implied_volatility": 0.0},
        ]
        result = compute_atm_iv(puts, spot=100.0)
        self.assertIsNone(result)

    def test_single_put(self):
        puts = [{"strike": 100.0, "implied_volatility": 0.28}]
        result = compute_atm_iv(puts, spot=100.0)
        self.assertAlmostEqual(result, 0.28)


class SelectIv30FromExpiriesTest(TestCase):

    def test_picks_closest_to_30_dte(self):
        expiry_ivs = [(25, 0.30), (35, 0.28), (45, 0.26)]
        result = select_iv30_from_expiries(expiry_ivs)
        self.assertAlmostEqual(result, 0.30)  # 25 DTE is closest to 30

    def test_exact_30_dte(self):
        expiry_ivs = [(30, 0.32), (45, 0.26)]
        result = select_iv30_from_expiries(expiry_ivs)
        self.assertAlmostEqual(result, 0.32)

    def test_empty_list(self):
        result = select_iv30_from_expiries([])
        self.assertIsNone(result)
