from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("kern", "0007_konto_admin_bis"),
    ]

    operations = [
        migrations.AddField(
            model_name="konto",
            name="zugang_stand",
            field=models.PositiveIntegerField(default=0, editable=False),
        ),
    ]
