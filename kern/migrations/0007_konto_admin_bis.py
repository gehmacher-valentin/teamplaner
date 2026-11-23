from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("kern", "0006_platzhalter_weiterleiten"),
    ]

    operations = [
        migrations.AddField(
            model_name="konto",
            name="admin_bis",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
    ]
