from django.db import migrations


def seed_min_avg_volume(apps, schema_editor):
    FilterConfig = apps.get_model("screener", "FilterConfig")
    FilterConfig.objects.get_or_create(
        key="min_avg_volume",
        defaults={
            "value": "1.5",
            "value_type": "float",
            "description": "Minimum 10-day average trading volume (millions of shares)",
        },
    )


def reverse_seed(apps, schema_editor):
    FilterConfig = apps.get_model("screener", "FilterConfig")
    FilterConfig.objects.filter(key="min_avg_volume").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("screener", "0005_seed_min_notional_oi"),
    ]

    operations = [
        migrations.RunPython(seed_min_avg_volume, reverse_code=reverse_seed),
    ]
