from django.db import models


class Symbol(models.Model):
    ticker = models.CharField(max_length=10, unique=True, db_index=True)
    exchange_mic = models.CharField(max_length=10)
    name = models.CharField(max_length=255)
    market_cap = models.BigIntegerField(null=True, blank=True)
    operating_margin = models.FloatField(null=True, blank=True)
    free_cash_flow = models.FloatField(null=True, blank=True)
    debt_to_equity = models.FloatField(null=True, blank=True)
    avg_volume_10d = models.FloatField(null=True, blank=True)
    has_options = models.BooleanField(
        default=True,
        help_text="False if yfinance reports no options chain — skipped in IV pulls",
    )
    suppress_until = models.DateField(
        null=True, blank=True,
        help_text="Hide from candidates until this date (exclusive — reappears day after)",
    )
    fundamentals_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["ticker"]

    def __str__(self):
        return self.ticker


class EarningsDate(models.Model):
    symbol = models.ForeignKey(Symbol, on_delete=models.CASCADE, related_name="earnings_dates")
    report_date = models.DateField()
    source = models.CharField(max_length=50, default="finnhub")
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["symbol", "report_date"]
        ordering = ["report_date"]


class IVRank(models.Model):
    symbol = models.ForeignKey(Symbol, on_delete=models.CASCADE, related_name="iv_ranks")
    computed_date = models.DateField()
    iv_rank = models.FloatField(help_text="0-100 scale")
    iv_percentile = models.FloatField(null=True, blank=True)
    weeks_of_history = models.IntegerField(default=0)
    is_reliable = models.BooleanField(default=False, help_text="True when >= 52 weeks of history")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["symbol"], name="unique_ivrank_per_symbol"),
        ]


class IV30Snapshot(models.Model):
    symbol = models.ForeignKey(Symbol, on_delete=models.CASCADE, related_name="iv30_snapshots")
    date = models.DateField()
    iv30 = models.FloatField(help_text="30-day implied volatility (decimal, e.g. 0.28)")

    class Meta:
        unique_together = ["symbol", "date"]
        ordering = ["-date"]

    def __str__(self):
        return f"{self.symbol.ticker} {self.date} IV30={self.iv30}"


class FilterConfig(models.Model):
    VALUE_TYPES = [
        ("int", "Integer"),
        ("float", "Float"),
        ("bool", "Boolean"),
    ]

    key = models.CharField(max_length=100, unique=True)
    value = models.CharField(max_length=100)
    value_type = models.CharField(max_length=10, choices=VALUE_TYPES, default="float")
    description = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def typed_value(self):
        if self.value_type == "int":
            return int(self.value)
        elif self.value_type == "float":
            return float(self.value)
        elif self.value_type == "bool":
            return self.value.lower() in ("true", "1", "yes")
        return self.value

    @classmethod
    def get_value(cls, key):
        """Get typed value for a config key. Raises DoesNotExist if missing."""
        return cls.objects.get(key=key).typed_value

    def __str__(self):
        return f"{self.key} = {self.value}"
