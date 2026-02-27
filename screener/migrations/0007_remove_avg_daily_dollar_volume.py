from django.db import migrations


def remove_dead_key(apps, schema_editor):
    FilterConfig = apps.get_model("screener", "FilterConfig")
    FilterConfig.objects.filter(key="avg_daily_dollar_volume_min").delete()


def restore_key(apps, schema_editor):
    FilterConfig = apps.get_model("screener", "FilterConfig")
    FilterConfig.objects.get_or_create(
        key="avg_daily_dollar_volume_min",
        defaults={
            "value": "100000000",
            "value_type": "int",
            "description": "Minimum 10-day avg dollar volume ($100M)",
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ("screener", "0006_seed_min_avg_volume"),
    ]

    operations = [
        migrations.RunPython(remove_dead_key, reverse_code=restore_key),
    ]
