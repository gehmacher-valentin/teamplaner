
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('kern', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Bestellung',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('prio', models.BooleanField(default=False, verbose_name='Prio')),
                ('bedarf', models.CharField(max_length=500, verbose_name='Bedarf')),
                ('aufnahmedatum', models.DateField(default=django.utils.timezone.localdate, verbose_name='Aufnahmedatum')),
                ('projekt', models.CharField(blank=True, max_length=200, verbose_name='Projekt')),
                ('bestellt_am', models.DateField(blank=True, null=True, verbose_name='Bestellt am')),
                ('lieferant', models.CharField(blank=True, max_length=200, verbose_name='Lieferant')),
                ('liefertermin', models.DateField(blank=True, null=True, verbose_name='Liefertermin')),
                ('warnung_fuer_termin', models.DateField(blank=True, editable=False, null=True)),
                ('status', models.CharField(choices=[('offen', 'offen'), ('recherche', 'Recherche'), ('bestellt', 'bestellt'), ('erhalten', 'erhalten'), ('achtung', 'Achtung')], default='offen', max_length=20, verbose_name='Status')),
                ('erstellt_am', models.DateTimeField(auto_now_add=True)),
                ('geaendert_am', models.DateTimeField(auto_now=True)),
                ('bestellt_von', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='kern.person', verbose_name='Bestellt von')),
                ('eingetragen_von', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='kern.person', verbose_name='Eingetragen von')),
                ('erstellt_von', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='kern.person')),
            ],
            options={
                'verbose_name': 'Bestellung',
                'verbose_name_plural': 'Bestellungen',
                'ordering': ['-aufnahmedatum', '-id'],
            },
        ),
    ]
