
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
            name='GanttAnsicht',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, verbose_name='Name')),
                ('sortierung', models.PositiveIntegerField(default=0, verbose_name='Sortierung')),
                ('neue_projekte_automatisch', models.BooleanField(default=False, verbose_name='Neue Projekte automatisch aufnehmen')),
                ('erstellt_am', models.DateTimeField(auto_now_add=True)),
                ('geaendert_am', models.DateTimeField(auto_now=True)),
                ('erstellt_von', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='kern.person')),
                ('projekte', models.ManyToManyField(blank=True, related_name='gantt_ansichten', to='projekte.projekt', verbose_name='Projekte')),
            ],
            options={
                'verbose_name': 'Gantt-Ansicht',
                'verbose_name_plural': 'Gantt-Ansichten',
                'ordering': ['sortierung', 'name', 'id'],
            },
        ),
        migrations.CreateModel(
            name='GanttFreigabe',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('recht', models.CharField(choices=[('sehen', 'nur sehen'), ('bearbeiten', 'bearbeiten')], max_length=20, verbose_name='Recht')),
                ('ansicht', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='freigaben', to='gantt.ganttansicht')),
                ('konto', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='gantt_freigaben', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Gantt-Freigabe',
                'verbose_name_plural': 'Gantt-Freigaben',
                'constraints': [models.UniqueConstraint(fields=('ansicht', 'konto'), name='gantt_freigabe_eindeutig')],
            },
        ),
    ]
