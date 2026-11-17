import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projekte', '0003_gruppe'),
    ]

    operations = [
        migrations.AddField(
            model_name='aufgabe',
            name='wiederholung',
            field=models.JSONField(blank=True, null=True, verbose_name='Wiederholung'),
        ),
        migrations.AddField(
            model_name='aufgabe',
            name='wiederholt_von',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='folgeaufgabe', to='projekte.aufgabe', verbose_name='Wiederholung von'),
        ),
    ]
