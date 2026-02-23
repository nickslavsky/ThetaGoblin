from django.test import TestCase
from screener.services.options_math import compute_put_delta


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
