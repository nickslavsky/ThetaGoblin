from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("screener", "0014_iv30_yfinance_nullable"),
    ]

    operations = [
        # Step 1: Drop the old DoltHub iv30 column
        migrations.RemoveField(
            model_name="iv30snapshot",
            name="iv30",
        ),
        # Step 2: Rename iv30_yfinance → iv30
        migrations.RenameField(
            model_name="iv30snapshot",
            old_name="iv30_yfinance",
            new_name="iv30",
        ),
        # Step 3: Make NOT NULL (user confirmed no null/zero rows exist)
        migrations.AlterField(
            model_name="iv30snapshot",
            name="iv30",
            field=models.FloatField(
                help_text="30-day implied volatility (decimal, e.g. 0.28)"
            ),
        ),
    ]
