from django.db import migrations

STATUS = [
    ("Offen", False, "grau"),
    ("Eingeplant", False, "blau"),
    ("In Arbeit", False, "gelb"),
    ("Wartet", False, "orange"),
    ("Erledigt", True, "gruen"),
]


def status_anlegen(apps, schema_editor):
    Status = apps.get_model("projekte", "Status")
    for i, (name, erledigt, farbe) in enumerate(STATUS):
        Status.objects.get_or_create(
            name=name, defaults={"sortierung": i, "ist_erledigt": erledigt, "farbe": farbe}
        )


class Migration(migrations.Migration):
    dependencies = [("projekte", "0001_initial")]

    operations = [migrations.RunPython(status_anlegen, migrations.RunPython.noop)]
