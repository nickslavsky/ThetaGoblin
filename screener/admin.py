from django.contrib import admin

from screener.models import EarningsDate, FilterConfig, IV30Snapshot, IVRank, OptionsSnapshot, Symbol


@admin.register(FilterConfig)
class FilterConfigAdmin(admin.ModelAdmin):
    list_display = ["key", "value", "value_type", "description", "updated_at"]
    list_editable = ["value"]
    list_display_links = ["key"]
    search_fields = ["key", "description"]
    list_per_page = 50
    ordering = ["key"]


@admin.register(Symbol)
class SymbolAdmin(admin.ModelAdmin):
    list_display = [
        "ticker", "name", "exchange_mic", "market_cap",
        "operating_margin", "ten_day_avg_trading_volume", "fundamentals_updated_at",
    ]
    list_filter = ["exchange_mic"]
    search_fields = ["ticker", "name"]
    readonly_fields = ["fundamentals_updated_at"]
    ordering = ["ticker"]


@admin.register(EarningsDate)
class EarningsDateAdmin(admin.ModelAdmin):
    list_display = ["symbol", "report_date", "source", "last_updated"]
    list_filter = ["source"]
    search_fields = ["symbol__ticker"]
    ordering = ["-report_date"]


@admin.register(OptionsSnapshot)
class OptionsSnapshotAdmin(admin.ModelAdmin):
    list_display = [
        "symbol", "snapshot_date", "expiry_date", "dte_at_snapshot",
        "strike", "spot_price", "delta", "bid", "ask",
    ]
    list_filter = ["snapshot_date", "expiry_date"]
    search_fields = ["symbol__ticker"]
    ordering = ["-snapshot_date", "symbol", "expiry_date", "strike"]


@admin.register(IV30Snapshot)
class IV30SnapshotAdmin(admin.ModelAdmin):
    list_display = ["symbol", "date", "iv30"]
    list_filter = ["date"]
    search_fields = ["symbol__ticker"]
    ordering = ["-date"]


@admin.register(IVRank)
class IVRankAdmin(admin.ModelAdmin):
    list_display = [
        "symbol", "computed_date", "iv_rank", "iv_percentile",
        "is_reliable", "weeks_of_history",
    ]
    list_filter = ["is_reliable"]
    search_fields = ["symbol__ticker"]
    ordering = ["symbol__ticker"]
