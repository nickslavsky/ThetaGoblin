import csv
import os
import tempfile
from django.test import TestCase
from django.core.management import call_command
from screener.models import Symbol


class LoadSymbolsTest(TestCase):

    def _write_csv(self, rows):
        """Helper: write rows to a temp CSV file, return path."""
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="")
        writer = csv.DictWriter(f, fieldnames=[
            "ticker", "exchange_mic", "name", "market_cap",
            "operating_margin", "cash_flow_per_share_annual",
            "long_term_debt_to_equity_annual", "ten_day_avg_trading_volume",
        ])
        writer.writeheader()
        writer.writerows(rows)
        f.close()
        return f.name

    def tearDown(self):
        # Clean up any temp files
        pass

    def test_load_creates_symbols(self):
        rows = [
            {"ticker": "AAPL", "exchange_mic": "XNAS", "name": "Apple Inc",
             "market_cap": "3000000000000", "operating_margin": "0.30",
             "cash_flow_per_share_annual": "7.5", "long_term_debt_to_equity_annual": "1.2",
             "ten_day_avg_trading_volume": "5000000"},
            {"ticker": "MSFT", "exchange_mic": "XNAS", "name": "Microsoft Corp",
             "market_cap": "2800000000000", "operating_margin": "0.42",
             "cash_flow_per_share_annual": "11.0", "long_term_debt_to_equity_annual": "0.5",
             "ten_day_avg_trading_volume": "3000000"},
        ]
        path = self._write_csv(rows)
        try:
            call_command("load_symbols", path)
            self.assertEqual(Symbol.objects.count(), 2)
        finally:
            os.unlink(path)

    def test_load_is_idempotent(self):
        rows = [
            {"ticker": "GOOG", "exchange_mic": "XNAS", "name": "Alphabet Inc",
             "market_cap": "2000000000000", "operating_margin": "0.25",
             "cash_flow_per_share_annual": "5.0", "long_term_debt_to_equity_annual": "0.1",
             "ten_day_avg_trading_volume": "1000000"},
        ]
        path = self._write_csv(rows)
        try:
            call_command("load_symbols", path)
            call_command("load_symbols", path)
            self.assertEqual(Symbol.objects.count(), 1)  # No duplicates
        finally:
            os.unlink(path)

    def test_load_updates_existing(self):
        Symbol.objects.create(
            ticker="TSLA", exchange_mic="XNAS", name="Tesla Inc",
            market_cap=500_000_000_000,
        )
        rows = [
            {"ticker": "TSLA", "exchange_mic": "XNAS", "name": "Tesla Inc",
             "market_cap": "600000000000", "operating_margin": "0.08",
             "cash_flow_per_share_annual": "3.0", "long_term_debt_to_equity_annual": "0.8",
             "ten_day_avg_trading_volume": "2000000"},
        ]
        path = self._write_csv(rows)
        try:
            call_command("load_symbols", path)
            tsla = Symbol.objects.get(ticker="TSLA")
            self.assertEqual(Symbol.objects.count(), 1)
            self.assertEqual(tsla.market_cap, 600_000_000_000)
        finally:
            os.unlink(path)

    def test_load_handles_missing_optional_fields(self):
        """Rows with empty optional fields should still import."""
        rows = [
            {"ticker": "XYZ", "exchange_mic": "XNYS", "name": "XYZ Corp",
             "market_cap": "50000000000", "operating_margin": "",
             "cash_flow_per_share_annual": "", "long_term_debt_to_equity_annual": "",
             "ten_day_avg_trading_volume": ""},
        ]
        path = self._write_csv(rows)
        try:
            call_command("load_symbols", path)
            xyz = Symbol.objects.get(ticker="XYZ")
            self.assertIsNone(xyz.operating_margin)
        finally:
            os.unlink(path)
