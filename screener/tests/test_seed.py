from django.test import TestCase
from screener.models import FilterConfig


class FilterConfigSeedTest(TestCase):
    """Migrations run automatically in test DB, so seeds should exist."""

    def test_all_default_keys_exist(self):
        expected_keys = [
            "market_cap_min", "operating_margin_min", "free_cash_flow_min",
            "min_avg_volume", "debt_to_equity_max",
            "earnings_exclusion_days", "iv_rank_min", "iv_rank_max",
            "iv_min", "iv_max", "delta_target_min", "delta_target_max",
            "otm_pct_target", "expiry_dte_min", "expiry_dte_max",
            "risk_free_rate", "min_notional_oi",
        ]
        for key in expected_keys:
            self.assertTrue(
                FilterConfig.objects.filter(key=key).exists(),
                f"Missing seed key: {key}",
            )

    def test_market_cap_min_typed_value(self):
        val = FilterConfig.get_value("market_cap_min")
        self.assertEqual(val, 10_000_000_000)

    def test_risk_free_rate_typed_value(self):
        val = FilterConfig.get_value("risk_free_rate")
        self.assertAlmostEqual(val, 0.043)

    def test_earnings_exclusion_days_is_int(self):
        val = FilterConfig.get_value("earnings_exclusion_days")
        self.assertIsInstance(val, int)
        self.assertEqual(val, 50)

    def test_iv_rank_min_is_float(self):
        val = FilterConfig.get_value("iv_rank_min")
        self.assertIsInstance(val, float)
        self.assertAlmostEqual(val, 70.0)
