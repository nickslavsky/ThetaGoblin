from datetime import date
from django.test import TestCase
from screener.services.iv_rank_svc import compute_iv_rank


class ComputeIVRankTest(TestCase):

    def test_normal_case(self):
        result = compute_iv_rank(
            current_iv30=0.30,
            min_iv30=0.20,
            max_iv30=0.40,
            count_lte=3,
            total_count=5,
            earliest_date=date(2026, 1, 1),
            latest_date=date(2026, 3, 12),  # 70 days = 10 weeks
        )
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["iv_rank"], 50.0)
        self.assertAlmostEqual(result["iv_percentile"], 60.0)
        self.assertEqual(result["weeks_of_history"], 10)
        self.assertFalse(result["is_reliable"])

    def test_at_bottom(self):
        result = compute_iv_rank(
            current_iv30=0.20,
            min_iv30=0.20,
            max_iv30=0.40,
            count_lte=1,
            total_count=3,
            earliest_date=date(2026, 1, 1),
            latest_date=date(2026, 2, 1),
        )
        self.assertAlmostEqual(result["iv_rank"], 0.0)

    def test_at_top(self):
        result = compute_iv_rank(
            current_iv30=0.40,
            min_iv30=0.20,
            max_iv30=0.40,
            count_lte=3,
            total_count=3,
            earliest_date=date(2026, 1, 1),
            latest_date=date(2026, 2, 1),
        )
        self.assertAlmostEqual(result["iv_rank"], 100.0)

    def test_percentile(self):
        result = compute_iv_rank(
            current_iv30=0.30,
            min_iv30=0.20,
            max_iv30=0.40,
            count_lte=3,
            total_count=5,
            earliest_date=date(2026, 1, 1),
            latest_date=date(2026, 2, 1),
        )
        self.assertAlmostEqual(result["iv_percentile"], 60.0)

    def test_all_same_returns_none(self):
        result = compute_iv_rank(
            current_iv30=0.30,
            min_iv30=0.30,
            max_iv30=0.30,
            count_lte=3,
            total_count=3,
            earliest_date=date(2026, 1, 1),
            latest_date=date(2026, 2, 1),
        )
        self.assertIsNone(result)

    def test_single_point_returns_none(self):
        result = compute_iv_rank(
            current_iv30=0.30,
            min_iv30=0.30,
            max_iv30=0.30,
            count_lte=1,
            total_count=1,
            earliest_date=date(2026, 1, 1),
            latest_date=date(2026, 1, 1),
        )
        self.assertIsNone(result)

    def test_reliable_365_day_span(self):
        result = compute_iv_rank(
            current_iv30=0.30,
            min_iv30=0.20,
            max_iv30=0.40,
            count_lte=100,
            total_count=252,
            earliest_date=date(2025, 3, 1),
            latest_date=date(2026, 3, 1),  # 365 days
        )
        self.assertTrue(result["is_reliable"])
        self.assertEqual(result["weeks_of_history"], 52)

    def test_not_reliable_short_span(self):
        result = compute_iv_rank(
            current_iv30=0.30,
            min_iv30=0.20,
            max_iv30=0.40,
            count_lte=30,
            total_count=70,
            earliest_date=date(2025, 11, 27),
            latest_date=date(2026, 3, 6),  # 100 days
        )
        self.assertFalse(result["is_reliable"])
        self.assertEqual(result["weeks_of_history"], 14)
