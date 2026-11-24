from django.db import migrations


def herabsetzen(apps, schema_editor):
    """Admin-Konten, deren Daten nach der Frist entfernt wurden: Rolle „Lesend“, wie es
    ``verwaltung.aufraeumen`` ab jetzt selbst macht. Nur Konten ohne Passwort – mit dem Befehl
    konto_aendern könnte eines inzwischen wieder benutzt werden."""
    Konto = apps.get_model("kern", "Konto")
    Protokolleintrag = apps.get_model("kern", "Protokolleintrag")
    for konto in Konto.objects.filter(rolle="admin", email__endswith="@konto.invalid", password__startswith="!"):
        konto.rolle, konto.admin_bis = "lesend", None
        konto.save(update_fields=["rolle", "admin_bis"])
        Protokolleintrag.objects.create(
            objekt_typ="konto", objekt_id=konto.pk, aktion="geaendert",
            daten={"person": {"id": konto.pk, "name": konto.person.anzeigename}, "rolle": ["admin", "lesend"]})


class Migration(migrations.Migration):

    dependencies = [
        ("kern", "0008_konto_zugang_stand"),
    ]

    operations = [
        migrations.RunPython(herabsetzen, migrations.RunPython.noop),
    ]
