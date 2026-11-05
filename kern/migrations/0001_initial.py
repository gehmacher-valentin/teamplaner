
import django.db.models.deletion
import django.db.models.functions.text
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Bereich',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True, verbose_name='Name')),
                ('sortierung', models.PositiveIntegerField(default=0, verbose_name='Sortierung')),
            ],
            options={
                'verbose_name': 'Bereich',
                'verbose_name_plural': 'Bereiche',
                'ordering': ['sortierung', 'name'],
            },
        ),
        migrations.CreateModel(
            name='Gewerk',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True, verbose_name='Name')),
            ],
            options={
                'verbose_name': 'Gewerk',
                'verbose_name_plural': 'Gewerke',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='Resetanfrage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('zeitpunkt', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('ip', models.GenericIPAddressField(blank=True, null=True)),
                ('email_hash', models.CharField(max_length=64)),
            ],
        ),
        migrations.CreateModel(
            name='Systemeinstellungen',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('freigabe_zeile', models.BooleanField(default=False, verbose_name='Tagesfreigabe')),
                ('freigabe_name', models.CharField(blank=True, max_length=40, verbose_name='Name der Tagesfreigabe')),
                ('organisation', models.CharField(blank=True, max_length=100, verbose_name='Organisationsname')),
                ('mail_versand', models.BooleanField(default=True, verbose_name='E-Mail-Versand')),
            ],
            options={
                'verbose_name': 'Systemeinstellungen',
                'verbose_name_plural': 'Systemeinstellungen',
            },
        ),
        migrations.CreateModel(
            name='Person',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('anzeigename', models.CharField(max_length=150, verbose_name='Anzeigename')),
                ('notiz', models.CharField(blank=True, max_length=500, verbose_name='Notiz')),
                ('foto', models.ImageField(blank=True, upload_to='fotos/', verbose_name='Foto')),
                ('archiviert_am', models.DateTimeField(blank=True, null=True, verbose_name='archiviert am')),
                ('erstellt_am', models.DateTimeField(auto_now_add=True)),
                ('erstellt_von', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='kern.person')),
                ('bereich', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='personen', to='kern.bereich', verbose_name='Bereich')),
                ('gewerke', models.ManyToManyField(blank=True, related_name='personen', to='kern.gewerk', verbose_name='Gewerke')),
            ],
            options={
                'verbose_name': 'Person',
                'verbose_name_plural': 'Personen',
                'ordering': ['anzeigename', 'id'],
            },
        ),
        migrations.CreateModel(
            name='Konto',
            fields=[
                ('password', models.CharField(max_length=128, verbose_name='password')),
                ('last_login', models.DateTimeField(blank=True, null=True, verbose_name='last login')),
                ('person', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, primary_key=True, related_name='konto', serialize=False, to='kern.person')),
                ('email', models.EmailField(max_length=254, unique=True, verbose_name='E-Mail')),
                ('rolle', models.CharField(choices=[('admin', 'Admin'), ('bereichsleitung', 'Bereichsleitung'), ('planer', 'Planer:in'), ('mitarbeiter', 'Mitarbeiter:in'), ('lesend', 'Lesend')], max_length=20, verbose_name='Rolle')),
                ('mail_einstellungen', models.JSONField(blank=True, default=dict, verbose_name='E-Mail-Benachrichtigungen')),
                ('sprache', models.CharField(choices=[('de', 'Deutsch'), ('en', 'English')], default='de', max_length=5, verbose_name='Sprache')),
                ('feier_animation', models.BooleanField(default=False, verbose_name='Feieranimation beim Abhaken')),
                ('gantt_unteraufgaben_offen', models.BooleanField(default=False, verbose_name='Unteraufgaben im Gantt aufgeklappt')),
                ('systemkonto', models.BooleanField(default=False, verbose_name='Systemkonto – nicht als Person auswählbar')),
                ('totp_geheimnis', models.CharField(blank=True, editable=False, max_length=64)),
                ('totp_seit', models.DateTimeField(blank=True, editable=False, null=True)),
                ('totp_letzter_schritt', models.BigIntegerField(blank=True, editable=False, null=True)),
                ('totp_ersatzcodes', models.JSONField(blank=True, default=list, editable=False)),
                ('daten_entfernt_am', models.DateTimeField(blank=True, editable=False, null=True)),
            ],
            options={
                'verbose_name': 'Konto',
                'verbose_name_plural': 'Konten',
                'constraints': [models.UniqueConstraint(django.db.models.functions.text.Lower('email'), name='konto_email_eindeutig_ci')],
            },
        ),
        migrations.CreateModel(
            name='Protokolleintrag',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('zeitpunkt', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('objekt_typ', models.CharField(max_length=40)),
                ('objekt_id', models.BigIntegerField(blank=True, null=True)),
                ('aufgabe_id', models.BigIntegerField(blank=True, db_index=True, null=True)),
                ('aktion', models.CharField(max_length=40)),
                ('daten', models.JSONField(blank=True, default=dict)),
                ('akteur', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='kern.person')),
            ],
            options={
                'verbose_name': 'Protokolleintrag',
                'verbose_name_plural': 'Protokoll',
                'ordering': ['-zeitpunkt', '-id'],
                'indexes': [models.Index(fields=['objekt_typ', 'objekt_id'], name='kern_protok_objekt__cc2a6b_idx')],
            },
        ),
    ]
