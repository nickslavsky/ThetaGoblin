from django.db import migrations


def seed_otm_pct_range(apps, schema_editor):
    FilterConfig = apps.get_model("screener", "FilterConfig")
    new_keys = [
        ("otm_pct_min", "0.15", "float", "Minimum OTM percentage for candidate puts (15%)"),
        ("otm_pct_max", "0.20", "float", "Maximum OTM percentage for candidate puts (20%)"),
    ]
    for key, value, value_type, description in new_keys:
        FilterConfig.objects.get_or_create(
            key=key,
            defaults={"value": value, "value_type": value_type, "description": description},
        )


def reverse_seed_otm_pct_range(apps, schema_editor):
    FilterConfig = apps.get_model("screener", "FilterConfig")
    FilterConfig.objects.filter(key__in=["otm_pct_min", "otm_pct_max"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("screener", "0002_seed_filterconfig"),
    ]

    operations = [
        migrations.RunPython(seed_otm_pct_range, reverse_code=reverse_seed_otm_pct_range),
    ]
