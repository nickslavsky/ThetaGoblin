from django.test import TestCase
from screener.services.iv_rank_svc import compute_iv_rank


class ComputeIVRankTest(TestCase):

    def test_normal_case(self):
        result = compute_iv_rank(0.30, [0.20, 0.25, 0.30, 0.35, 0.40])
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["iv_rank"], 50.0)
        self.assertEqual(result["weeks_of_history"], 5)
        self.assertFalse(result["is_reliable"])

    def test_at_bottom(self):
        result = compute_iv_rank(0.20, [0.20, 0.30, 0.40])
        self.assertAlmostEqual(result["iv_rank"], 0.0)

    def test_at_top(self):
        result = compute_iv_rank(0.40, [0.20, 0.30, 0.40])
        self.assertAlmostEqual(result["iv_rank"], 100.0)

    def test_percentile(self):
        # 3 out of 5 values are <= 0.30
        result = compute_iv_rank(0.30, [0.20, 0.25, 0.30, 0.35, 0.40])
        self.assertAlmostEqual(result["iv_percentile"], 60.0)

    def test_fewer_than_two_returns_none(self):
        self.assertIsNone(compute_iv_rank(0.30, [0.30]))

    def test_empty_returns_none(self):
        self.assertIsNone(compute_iv_rank(0.30, []))

    def test_all_same_returns_none(self):
        self.assertIsNone(compute_iv_rank(0.30, [0.30, 0.30, 0.30]))

    def test_52_weeks_is_reliable(self):
        history = [0.20 + i * 0.01 for i in range(52)]
        result = compute_iv_rank(0.50, history)
        self.assertTrue(result["is_reliable"])
        self.assertEqual(result["weeks_of_history"], 52)

    def test_51_weeks_not_reliable(self):
        history = [0.20 + i * 0.01 for i in range(51)]
        result = compute_iv_rank(0.50, history)
        self.assertFalse(result["is_reliable"])
        self.assertEqual(result["weeks_of_history"], 51)
