from django.db import migrations

BEREICHE = ["Allgemein"]

PROTOKOLL_SCHUTZ = """
CREATE OR REPLACE FUNCTION kern_protokoll_nur_einfuegen() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' AND OLD.zeitpunkt < now() - interval '365 days' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'Das Änderungsprotokoll ist unveränderlich (nur Einfügen; Löschen erst nach einem Jahr).';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER kern_protokoll_unveraenderlich
    BEFORE UPDATE OR DELETE ON kern_protokolleintrag
    FOR EACH ROW EXECUTE FUNCTION kern_protokoll_nur_einfuegen();
"""

PROTOKOLL_SCHUTZ_ENTFERNEN = """
DROP TRIGGER IF EXISTS kern_protokoll_unveraenderlich ON kern_protokolleintrag;
DROP FUNCTION IF EXISTS kern_protokoll_nur_einfuegen();
"""


def bereiche_anlegen(apps, schema_editor):
    Bereich = apps.get_model("kern", "Bereich")
    for i, name in enumerate(BEREICHE):
        Bereich.objects.get_or_create(name=name, defaults={"sortierung": i})


class Migration(migrations.Migration):
    dependencies = [("kern", "0001_initial")]

    operations = [
        migrations.RunPython(bereiche_anlegen, migrations.RunPython.noop),
        migrations.RunSQL(PROTOKOLL_SCHUTZ, PROTOKOLL_SCHUTZ_ENTFERNEN),
    ]
