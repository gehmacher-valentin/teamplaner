
import django.db.models.deletion
import django.utils.timezone
import zusammenarbeit.models
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('kern', '0001_initial'),
        ('projekte', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Anhang',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('datei', models.FileField(max_length=200, upload_to=zusammenarbeit.models.anhang_pfad)),
                ('dateiname', models.CharField(max_length=255, verbose_name='Dateiname')),
                ('groesse', models.PositiveBigIntegerField(verbose_name='Größe')),
                ('content_type', models.CharField(blank=True, max_length=120)),
                ('hochgeladen_am', models.DateTimeField(default=django.utils.timezone.now)),
                ('aufgabe', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='anhaenge', to='projekte.aufgabe')),
                ('hochgeladen_von', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='kern.person')),
            ],
            options={
                'verbose_name': 'Anhang',
                'verbose_name_plural': 'Anhänge',
                'ordering': ['hochgeladen_am', 'id'],
            },
        ),
        migrations.CreateModel(
            name='Kommentar',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('text', models.TextField(verbose_name='Text')),
                ('erstellt_am', models.DateTimeField(default=django.utils.timezone.now)),
                ('aufgabe', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='kommentare', to='projekte.aufgabe')),
                ('autor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='kern.person')),
            ],
            options={
                'verbose_name': 'Kommentar',
                'verbose_name_plural': 'Kommentare',
                'ordering': ['erstellt_am', 'id'],
            },
        ),
        migrations.CreateModel(
            name='Postausgang',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('art', models.CharField(choices=[('einladung', 'Einladung'), ('reset', 'Passwort zurücksetzen'), ('sicherheit', 'Sicherheitshinweis')], max_length=20)),
                ('empfaenger', models.EmailField(max_length=254)),
                ('betreff', models.CharField(max_length=200)),
                ('text', models.TextField(blank=True)),
                ('erstellt_am', models.DateTimeField(default=django.utils.timezone.now)),
                ('status', models.CharField(blank=True, choices=[('', 'keine E-Mail'), ('offen', 'wird verschickt'), ('gesendet', 'verschickt'), ('fehler', 'Fehler')], default='offen', max_length=10)),
                ('versuche', models.PositiveSmallIntegerField(default=0)),
                ('gesendet_am', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'verbose_name': 'System-Mail',
                'verbose_name_plural': 'Postausgang',
                'ordering': ['erstellt_am', 'id'],
                'indexes': [models.Index(fields=['status'], name='postausgang_status')],
            },
        ),
        migrations.CreateModel(
            name='Benachrichtigung',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('art', models.CharField(choices=[('zuweisung', 'Zuweisung'), ('aufgabe_geaendert', 'Aufgabe geändert'), ('aufgabe_erledigt', 'Aufgabe erledigt'), ('projekt_aufgabe_neu', 'Neue Aufgabe im Projekt'), ('erwaehnung', 'Erwähnung'), ('erwaehnung_platzhalter', 'Erwähnung eines Platzhalters'), ('kommentar', 'Kommentar'), ('einteilung_neu', 'Eingeteilt'), ('einteilung_geaendert', 'Einteilung geändert'), ('einteilung_entfernt', 'Einteilung entfernt'), ('liefertermin', 'Liefertermin überschritten')], max_length=30)),
                ('text', models.CharField(max_length=500)),
                ('erstellt_am', models.DateTimeField(default=django.utils.timezone.now)),
                ('gelesen_am', models.DateTimeField(blank=True, null=True)),
                ('mail_status', models.CharField(blank=True, choices=[('', 'keine E-Mail'), ('offen', 'wird verschickt'), ('gesendet', 'verschickt'), ('fehler', 'Fehler')], default='', max_length=10)),
                ('mail_versuche', models.PositiveSmallIntegerField(default=0)),
                ('gesendet_am', models.DateTimeField(blank=True, null=True)),
                ('aufgabe', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='+', to='projekte.aufgabe')),
                ('ausloeser', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='kern.person')),
                ('empfaenger', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='benachrichtigungen', to='kern.person')),
            ],
            options={
                'verbose_name': 'Benachrichtigung',
                'verbose_name_plural': 'Benachrichtigungen',
                'ordering': ['-erstellt_am', '-id'],
                'indexes': [models.Index(fields=['empfaenger', 'gelesen_am'], name='zusammenarb_empfaen_a08c7c_idx'), models.Index(fields=['mail_status'], name='zusammenarb_mail_st_abacfb_idx')],
            },
        ),
        migrations.CreateModel(
            name='Erwaehnung',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('person', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='erwaehnungen', to='kern.person')),
                ('kommentar', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='erwaehnungen', to='zusammenarbeit.kommentar')),
            ],
            options={
                'constraints': [models.UniqueConstraint(fields=('kommentar', 'person'), name='erwaehnung_eindeutig')],
            },
        ),
    ]
