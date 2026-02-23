from django.test import TestCase
from django.db import IntegrityError
from screener.models import Symbol, EarningsDate, OptionsSnapshot, IVRank, FilterConfig


class SymbolModelTest(TestCase):
    def test_str_returns_ticker(self):
        sym = Symbol.objects.create(ticker="AAPL", exchange_mic="XNAS", name="Apple Inc")
        self.assertEqual(str(sym), "AAPL")

    def test_unique_ticker(self):
        Symbol.objects.create(ticker="AAPL", exchange_mic="XNAS", name="Apple Inc")
        with self.assertRaises(Exception):
            Symbol.objects.create(ticker="AAPL", exchange_mic="XNAS", name="Apple Inc")


class EarningsDateModelTest(TestCase):
    def setUp(self):
        self.sym = Symbol.objects.create(ticker="AAPL", exchange_mic="XNAS", name="Apple Inc")

    def test_fk_cascade_delete(self):
        from datetime import date
        EarningsDate.objects.create(symbol=self.sym, report_date=date(2026, 4, 1))
        self.assertEqual(EarningsDate.objects.count(), 1)
        self.sym.delete()
        self.assertEqual(EarningsDate.objects.count(), 0)


class OptionsSnapshotModelTest(TestCase):
    def setUp(self):
        self.sym = Symbol.objects.create(ticker="AAPL", exchange_mic="XNAS", name="Apple Inc")

    def test_fk_cascade_delete(self):
        from datetime import date
        OptionsSnapshot.objects.create(
            symbol=self.sym,
            snapshot_date=date(2026, 2, 23),
            expiry_date=date(2026, 3, 21),
            dte_at_snapshot=26,
            strike="220.00",
            spot_price="230.00",
        )
        self.sym.delete()
        self.assertEqual(OptionsSnapshot.objects.count(), 0)


class IVRankModelTest(TestCase):
    def setUp(self):
        self.sym = Symbol.objects.create(ticker="AAPL", exchange_mic="XNAS", name="Apple Inc")

    def test_fk_cascade_delete(self):
        from datetime import date
        IVRank.objects.create(symbol=self.sym, computed_date=date(2026, 2, 23), iv_rank=75.0)
        self.sym.delete()
        self.assertEqual(IVRank.objects.count(), 0)


class FilterConfigModelTest(TestCase):
    def test_unique_key(self):
        FilterConfig.objects.create(key="test_key", value="1.0", value_type="float")
        with self.assertRaises(Exception):
            FilterConfig.objects.create(key="test_key", value="2.0", value_type="float")

    def test_typed_value_float(self):
        fc = FilterConfig(key="x", value="0.25", value_type="float")
        self.assertAlmostEqual(fc.typed_value, 0.25)

    def test_typed_value_int(self):
        fc = FilterConfig(key="x", value="100", value_type="int")
        self.assertEqual(fc.typed_value, 100)

    def test_typed_value_bool_true(self):
        fc = FilterConfig(key="x", value="true", value_type="bool")
        self.assertTrue(fc.typed_value)

    def test_typed_value_bool_false(self):
        fc = FilterConfig(key="x", value="false", value_type="bool")
        self.assertFalse(fc.typed_value)

    def test_get_value_classmethod(self):
        # market_cap_min is now seeded by migration; just read it directly
        val = FilterConfig.get_value("market_cap_min")
        self.assertEqual(val, 10_000_000_000)

    def test_str_representation(self):
        fc = FilterConfig(key="test", value="99")
        self.assertIn("test", str(fc))
        self.assertIn("99", str(fc))
