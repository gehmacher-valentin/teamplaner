
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('kern', '0001_initial'),
        ('projekte', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='FreierTag',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('datum', models.DateField(unique=True, verbose_name='Datum')),
                ('bezeichnung', models.CharField(max_length=100, verbose_name='Bezeichnung')),
            ],
            options={
                'verbose_name': 'Freier Tag',
                'verbose_name_plural': 'Freie Tage',
                'ordering': ['datum'],
            },
        ),
        migrations.CreateModel(
            name='FreigabeStufe',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=40, unique=True, verbose_name='Name')),
                ('sortierung', models.PositiveIntegerField(default=0, verbose_name='Sortierung')),
            ],
            options={
                'verbose_name': 'Freigabestufe',
                'verbose_name_plural': 'Freigabestufen',
                'ordering': ['sortierung', 'name'],
            },
        ),
        migrations.CreateModel(
            name='Tagesfreigabe',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('datum', models.DateField(unique=True, verbose_name='Datum')),
                ('geaendert_am', models.DateTimeField(auto_now=True)),
                ('geaendert_von', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='kern.person')),
                ('stufe', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='tage', to='planung.freigabestufe', verbose_name='Stufe')),
            ],
            options={
                'verbose_name': 'Tagesfreigabe',
                'verbose_name_plural': 'Tagesfreigaben',
                'ordering': ['datum'],
            },
        ),
        migrations.CreateModel(
            name='TagesInfo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('datum', models.DateField(unique=True, verbose_name='Datum')),
                ('text', models.CharField(max_length=120, verbose_name='Text')),
                ('geaendert_am', models.DateTimeField(auto_now=True)),
                ('geaendert_von', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='kern.person')),
            ],
            options={
                'verbose_name': 'Tagesinfo',
                'verbose_name_plural': 'Tagesinfos',
                'ordering': ['datum'],
            },
        ),
        migrations.CreateModel(
            name='TeamplanerAnsicht',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, verbose_name='Name')),
                ('sortierung', models.PositiveIntegerField(default=0, verbose_name='Sortierung')),
                ('filter', models.JSONField(blank=True, default=dict)),
                ('erstellt_am', models.DateTimeField(auto_now_add=True)),
                ('geaendert_am', models.DateTimeField(auto_now=True)),
                ('bereiche', models.ManyToManyField(blank=True, related_name='ansichten', to='kern.bereich', verbose_name='Bereiche')),
                ('erstellt_von', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='kern.person')),
                ('personen', models.ManyToManyField(blank=True, related_name='ansichten', to='kern.person', verbose_name='Einzelne Personen')),
            ],
            options={
                'verbose_name': 'Teamplaner-Ansicht',
                'verbose_name_plural': 'Teamplaner-Ansichten',
                'ordering': ['sortierung', 'name', 'id'],
            },
        ),
        migrations.CreateModel(
            name='Abwesenheit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('von', models.DateField()),
                ('bis', models.DateField()),
                ('version', models.PositiveIntegerField(default=1)),
                ('erstellt_am', models.DateTimeField(auto_now_add=True)),
                ('geaendert_am', models.DateTimeField(auto_now=True)),
                ('erstellt_von', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='kern.person')),
                ('person', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='abwesenheiten', to='kern.person')),
            ],
            options={
                'verbose_name': 'Abwesenheit',
                'verbose_name_plural': 'Abwesenheiten',
                'ordering': ['von', 'id'],
                'indexes': [models.Index(fields=['person', 'von', 'bis'], name='planung_abw_person__dadd18_idx')],
                'constraints': [models.CheckConstraint(condition=models.Q(('bis__gte', models.F('von'))), name='abwesenheit_bis_nach_von')],
            },
        ),
        migrations.CreateModel(
            name='Einteilung',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('von', models.DateField()),
                ('bis', models.DateField()),
                ('version', models.PositiveIntegerField(default=1)),
                ('erstellt_am', models.DateTimeField(auto_now_add=True)),
                ('geaendert_am', models.DateTimeField(auto_now=True)),
                ('aufgabe', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='einteilungen', to='projekte.aufgabe')),
                ('erstellt_von', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='kern.person')),
                ('person', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='einteilungen', to='kern.person')),
            ],
            options={
                'verbose_name': 'Einteilung',
                'verbose_name_plural': 'Einteilungen',
                'ordering': ['von', 'id'],
                'indexes': [models.Index(fields=['person', 'von', 'bis'], name='planung_ein_person__6a4d51_idx')],
                'constraints': [models.CheckConstraint(condition=models.Q(('bis__gte', models.F('von'))), name='einteilung_bis_nach_von')],
            },
        ),
        migrations.CreateModel(
            name='AnsichtFreigabe',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('recht', models.CharField(choices=[('sehen', 'nur sehen'), ('bearbeiten', 'bearbeiten')], max_length=20, verbose_name='Recht')),
                ('konto', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ansicht_freigaben', to=settings.AUTH_USER_MODEL)),
                ('ansicht', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='freigaben', to='planung.teamplaneransicht')),
            ],
            options={
                'verbose_name': 'Freigabe',
                'verbose_name_plural': 'Freigaben',
                'constraints': [models.UniqueConstraint(fields=('ansicht', 'konto'), name='freigabe_eindeutig')],
            },
        ),
    ]
