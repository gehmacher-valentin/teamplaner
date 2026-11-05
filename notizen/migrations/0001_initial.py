
import django.db.models.deletion
import django.db.models.functions.text
import django.utils.timezone
import notizen.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('kern', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Notiz',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('titel', models.CharField(max_length=200, verbose_name='Titel')),
                ('text', models.TextField(blank=True, verbose_name='Text')),
                ('version', models.PositiveIntegerField(default=1)),
                ('erstellt_am', models.DateTimeField(auto_now_add=True)),
                ('geaendert_am', models.DateTimeField(auto_now=True)),
                ('besitzer', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='notizen', to='kern.person')),
                ('erstellt_von', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='kern.person')),
                ('geaendert_von', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='kern.person')),
            ],
            options={
                'verbose_name': 'Notiz',
                'verbose_name_plural': 'Notizen',
                'ordering': ['-geaendert_am', '-id'],
            },
        ),
        migrations.CreateModel(
            name='NotizAnhang',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('datei', models.FileField(max_length=200, upload_to=notizen.models.anhang_pfad)),
                ('dateiname', models.CharField(max_length=255, verbose_name='Dateiname')),
                ('groesse', models.PositiveBigIntegerField(verbose_name='Größe')),
                ('content_type', models.CharField(blank=True, max_length=120)),
                ('hochgeladen_am', models.DateTimeField(default=django.utils.timezone.now)),
                ('hochgeladen_von', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='kern.person')),
                ('notiz', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='anhaenge', to='notizen.notiz')),
            ],
            options={
                'verbose_name': 'Anhang',
                'verbose_name_plural': 'Anhänge',
                'ordering': ['hochgeladen_am', 'id'],
            },
        ),
        migrations.CreateModel(
            name='Ordner',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, verbose_name='Name')),
                ('erstellt_am', models.DateTimeField(auto_now_add=True)),
                ('erstellt_von', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='kern.person')),
                ('mitglieder', models.ManyToManyField(blank=True, related_name='notizordner', to=settings.AUTH_USER_MODEL, verbose_name='Freigegeben für')),
            ],
            options={
                'verbose_name': 'Notizordner',
                'verbose_name_plural': 'Notizordner',
                'ordering': [django.db.models.functions.text.Lower('name'), 'id'],
            },
        ),
        migrations.AddField(
            model_name='notiz',
            name='ordner',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='notizen', to='notizen.ordner'),
        ),
        migrations.AddConstraint(
            model_name='notiz',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('besitzer__isnull', False), ('ordner__isnull', True)), models.Q(('besitzer__isnull', True), ('ordner__isnull', False)), _connector='OR'), name='notiz_ordner_oder_besitzer'),
        ),
    ]
