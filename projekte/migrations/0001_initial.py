
import django.core.validators
import django.db.models.deletion
import django.db.models.functions.text
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('kern', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Status',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=60, unique=True, verbose_name='Name')),
                ('sortierung', models.PositiveIntegerField(default=0, verbose_name='Sortierung')),
                ('ist_erledigt', models.BooleanField(default=False, verbose_name='gilt als erledigt')),
                ('farbe', models.CharField(choices=[('grau', 'Grau'), ('blau', 'Blau'), ('gelb', 'Gelb'), ('orange', 'Orange'), ('gruen', 'Grün')], default='grau', max_length=20, verbose_name='Farbe')),
            ],
            options={
                'verbose_name': 'Status',
                'verbose_name_plural': 'Status',
                'ordering': ['sortierung', 'id'],
            },
        ),
        migrations.CreateModel(
            name='Projekt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150, verbose_name='Name')),
                ('farbe', models.CharField(choices=[('bernstein', 'Bernstein'), ('blau', 'Blau'), ('gruen', 'Grün'), ('violett', 'Violett'), ('rot', 'Rot'), ('petrol', 'Petrol'), ('oliv', 'Oliv'), ('grau', 'Grau')], default='blau', max_length=20, verbose_name='Farbe')),
                ('beschreibung', models.TextField(blank=True, verbose_name='Beschreibung')),
                ('prioritaet', models.PositiveSmallIntegerField(blank=True, choices=[(1, '1'), (2, '2'), (3, '3'), (4, '4'), (5, '5')], null=True, verbose_name='Priorität')),
                ('archiviert_am', models.DateTimeField(blank=True, null=True, verbose_name='archiviert am')),
                ('beginn', models.DateField(blank=True, null=True, verbose_name='Beginn')),
                ('ende', models.DateField(blank=True, null=True, verbose_name='Ende')),
                ('erstellt_am', models.DateTimeField(auto_now_add=True)),
                ('erstellt_von', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='kern.person')),
                ('mitglieder', models.ManyToManyField(blank=True, related_name='projekte', to='kern.person', verbose_name='Mitglieder')),
                ('projektleitung', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='geleitete_projekte', to='kern.person', verbose_name='Projektleitung')),
            ],
            options={
                'verbose_name': 'Projekt',
                'verbose_name_plural': 'Projekte',
                'ordering': [models.OrderBy(models.F('prioritaet'), nulls_last=True), django.db.models.functions.text.Lower('name')],
            },
        ),
        migrations.CreateModel(
            name='Abschnitt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, verbose_name='Name')),
                ('sortierung', models.PositiveIntegerField(default=0)),
                ('projekt', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='abschnitte', to='projekte.projekt')),
            ],
            options={
                'verbose_name': 'Abschnitt',
                'verbose_name_plural': 'Abschnitte',
                'ordering': ['sortierung', 'id'],
            },
        ),
        migrations.CreateModel(
            name='Aufgabe',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('titel', models.CharField(max_length=300, verbose_name='Titel')),
                ('beschreibung', models.TextField(blank=True, verbose_name='Beschreibung')),
                ('beginn_am', models.DateField(blank=True, null=True, verbose_name='Geplanter Beginn')),
                ('faellig_am', models.DateField(blank=True, null=True, verbose_name='Fällig am')),
                ('schaetzung_personentage', models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True, validators=[django.core.validators.MinValueValidator(0)], verbose_name='Geschätzte Personentage')),
                ('sortierung', models.PositiveIntegerField(default=0)),
                ('erledigt_am', models.DateTimeField(blank=True, null=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('erstellt_am', models.DateTimeField(auto_now_add=True)),
                ('geaendert_am', models.DateTimeField(auto_now=True)),
                ('abschnitt', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='aufgaben', to='projekte.abschnitt', verbose_name='Abschnitt')),
                ('eltern', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='unteraufgaben', to='projekte.aufgabe', verbose_name='Hauptaufgabe')),
                ('erstellt_von', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='kern.person')),
                ('gewerk', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='aufgaben', to='kern.gewerk', verbose_name='Gewerk')),
                ('verantwortlich', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='verantwortete_aufgaben', to='kern.person', verbose_name='Verantwortlich')),
                ('projekt', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='aufgaben', to='projekte.projekt')),
                ('status', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='projekte.status', verbose_name='Status')),
            ],
            options={
                'verbose_name': 'Aufgabe',
                'verbose_name_plural': 'Aufgaben',
                'ordering': ['sortierung', 'id'],
            },
        ),
        migrations.CreateModel(
            name='Tag',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=60, verbose_name='Name')),
            ],
            options={
                'verbose_name': 'Tag',
                'verbose_name_plural': 'Tags',
                'ordering': [django.db.models.functions.text.Lower('name')],
                'constraints': [models.UniqueConstraint(django.db.models.functions.text.Lower('name'), name='tag_name_eindeutig_ci')],
            },
        ),
        migrations.AddField(
            model_name='projekt',
            name='tags',
            field=models.ManyToManyField(blank=True, related_name='projekte', to='projekte.tag', verbose_name='Tags'),
        ),
        migrations.CreateModel(
            name='Abhaengigkeit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('erstellt_am', models.DateTimeField(auto_now_add=True)),
                ('erstellt_von', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='kern.person')),
                ('nachher', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='vorgaenger_links', to='projekte.aufgabe')),
                ('vorher', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='nachfolger_links', to='projekte.aufgabe')),
            ],
            options={
                'verbose_name': 'Abhängigkeit',
                'verbose_name_plural': 'Abhängigkeiten',
                'constraints': [models.UniqueConstraint(fields=('vorher', 'nachher'), name='abhaengigkeit_eindeutig'), models.CheckConstraint(condition=models.Q(('vorher', models.F('nachher')), _negated=True), name='abhaengigkeit_nicht_selbst')],
            },
        ),
        migrations.AddIndex(
            model_name='aufgabe',
            index=models.Index(fields=['projekt', 'abschnitt', 'sortierung'], name='projekte_au_projekt_292f8a_idx'),
        ),
        migrations.AddIndex(
            model_name='aufgabe',
            index=models.Index(fields=['faellig_am'], name='projekte_au_faellig_a9416a_idx'),
        ),
    ]
