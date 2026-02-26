from django.db import migrations


def seed_min_notional_oi(apps, schema_editor):
    FilterConfig = apps.get_model("screener", "FilterConfig")
    FilterConfig.objects.get_or_create(
        key="min_notional_oi",
        defaults={
            "value": "10000000",
            "value_type": "int",
            "description": "Minimum notional open interest (avg OI x avg strike) — liquidity floor",
        },
    )


def reverse_seed(apps, schema_editor):
    FilterConfig = apps.get_model("screener", "FilterConfig")
    FilterConfig.objects.filter(key="min_notional_oi").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("screener", "0004_iv30snapshot"),
    ]

    operations = [
        migrations.RunPython(seed_min_notional_oi, reverse_code=reverse_seed),
    ]
