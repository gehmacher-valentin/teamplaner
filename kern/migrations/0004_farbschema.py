from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kern', '0003_gruppe'),
    ]

    operations = [
        migrations.AddField(
            model_name='konto',
            name='farbschema',
            field=models.CharField(choices=[('system', 'Wie am Gerät'), ('light', 'Hell'), ('dark', 'Dunkel')], default='system', max_length=10, verbose_name='Farbschema'),
        ),
    ]
