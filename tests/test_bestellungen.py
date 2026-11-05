"""Bestellungsverfolgung: ab Mitarbeiter:in eintragen und ändern, „Lesend“ nur lesen, alles im Protokoll;
Sortierung offen oben, erhalten unten."""

import pytest
from django.test import Client

from bestellungen.models import Bestellung
from kern.models import Rolle

pytestmark = pytest.mark.django_db

A, BL, P, M, L = Rolle.ADMIN, Rolle.BEREICHSLEITUNG, Rolle.PLANER, Rolle.MITARBEITER, Rolle.LESEND


def client_fuer(konto):
    c = Client()
    c.force_login(konto)
    return c


def test_ab_mitarbeiter_eintragen_und_aendern_lesend_nur_lesen(konten):
    from kern.models import Protokolleintrag

    for i, rolle in enumerate([A, BL, P, M, L]):
        antwort = client_fuer(konten[rolle]).post("/bestellungen/neu/", {
            "neu-bedarf": f"Bedarf {i}", "neu-aufnahmedatum": "2026-10-23", "neu-projekt": "Neubau Lagerhalle",
            "neu-lieferant": "", "neu-status": "offen",
        })
        assert antwort.status_code == (403 if rolle == L else 302)
    b = Bestellung.objects.get(bedarf="Bedarf 0")
    assert client_fuer(konten[L]).post(f"/bestellungen/{b.pk}/", {"status": "bestellt"}).status_code == 403
    assert client_fuer(konten[L]).get("/bestellungen/").status_code == 200
    antwort = client_fuer(konten[M]).post(f"/bestellungen/{b.pk}/", {"status": "bestellt", "bestellt_am": "2026-10-24"},
                                          HTTP_HX_REQUEST="true")
    assert antwort.status_code == 200
    b.refresh_from_db()
    assert b.status == "bestellt" and b.bestellt_am.isoformat() == "2026-10-24" and b.bedarf == "Bedarf 0"
    eintrag = Protokolleintrag.objects.get(objekt_typ="bestellung", objekt_id=b.pk, aktion="geaendert")
    assert eintrag.daten["status"] == ["offen", "bestellt"] and eintrag.akteur == konten[M].person


def test_sortierung_offen_oben_erhalten_unten(konten):
    for bedarf, status in [("Fertig", "erhalten"), ("Bestellt", "bestellt"), ("Neu", "offen"), ("Problem", "achtung")]:
        Bestellung.objects.create(bedarf=bedarf, status=status)
    seite = client_fuer(konten[M]).get("/bestellungen/").content.decode()
    positionen = [seite.index(f">{b}</textarea>") for b in ("Neu", "Problem", "Bestellt", "Fertig")]
    assert positionen == sorted(positionen)


def test_status_und_spalte_in_der_liste(konten):
    """Status „erhalten“ und Spalte „Eingetragen“ in der Oberfläche."""
    Bestellung.objects.create(bedarf="Neu", status="offen")
    Bestellung.objects.create(bedarf="Fertig", status="erhalten")
    seite = client_fuer(konten[M]).get("/bestellungen/").content.decode()
    assert '<option value="erhalten" selected>erhalten</option>' in seite
    assert ">Erhalten</div>" in seite and "<div>Eingetragen</div>" in seite


def test_loeschen_nur_eigene_oder_ab_planer(konten):
    b = Bestellung.objects.create(bedarf="Kleber", erstellt_von=konten[M].person)
    assert client_fuer(konten[L]).post(f"/bestellungen/{b.pk}/loeschen/").status_code == 403
    assert client_fuer(konten[M]).post(f"/bestellungen/{b.pk}/loeschen/").status_code == 302
    b = Bestellung.objects.create(bedarf="Schrauben", erstellt_von=konten[M].person)
    assert client_fuer(konten[P]).post(f"/bestellungen/{b.pk}/loeschen/").status_code == 302
    assert not Bestellung.objects.exists()


def test_ungueltiger_status_wird_nicht_gespeichert(konten):
    b = Bestellung.objects.create(bedarf="Kleber")
    antwort = client_fuer(konten[M]).post(f"/bestellungen/{b.pk}/", {"status": "weg"}, HTTP_HX_REQUEST="true")
    assert antwort["X-Fehler"] == "1"
    b.refresh_from_db()
    assert b.status == "offen"


# --- Prio ---

def test_prio_setzen_entfernen_protokoll_und_keine_sortierung(konten):
    from kern.models import Protokolleintrag

    alt = Bestellung.objects.create(bedarf="Alt", aufnahmedatum="2026-10-01")
    neu = Bestellung.objects.create(bedarf="Neu", aufnahmedatum="2026-10-20")
    c = client_fuer(konten[M])
    # Die Zeile schickt immer ein verstecktes „false“ und – wenn angehakt – danach „true“
    c.post(f"/bestellungen/{alt.pk}/", {"prio": ["false", "true"], "bedarf": "Alt"}, HTTP_HX_REQUEST="true")
    alt.refresh_from_db()
    assert alt.prio is True
    eintrag = Protokolleintrag.objects.get(objekt_typ="bestellung", objekt_id=alt.pk, aktion="geaendert")
    assert eintrag.daten["prio"] == [False, True]
    seite = c.get("/bestellungen/").content.decode()
    assert seite.index(">Neu</textarea>") < seite.index(">Alt</textarea>")  # Prio sortiert nicht
    c.post(f"/bestellungen/{alt.pk}/", {"prio": "false"}, HTTP_HX_REQUEST="true")
    alt.refresh_from_db()
    assert alt.prio is False
    # Andere Felder ohne Prio-Feld lassen sie unverändert
    neu.prio = True
    neu.save()
    c.post(f"/bestellungen/{neu.pk}/", {"projekt": "Neubau Lagerhalle"}, HTTP_HX_REQUEST="true")
    neu.refresh_from_db()
    assert neu.prio is True and neu.projekt == "Neubau Lagerhalle"


def test_prio_in_neuer_zeile_und_lesend_darf_nicht(konten):
    c = client_fuer(konten[M])
    c.post("/bestellungen/neu/", {"neu-prio": "true", "neu-bedarf": "Dringend", "neu-aufnahmedatum": "2026-11-03",
                                  "neu-status": "offen"})
    c.post("/bestellungen/neu/", {"neu-bedarf": "Normal", "neu-aufnahmedatum": "2026-11-03", "neu-status": "offen"})
    assert Bestellung.objects.get(bedarf="Dringend").prio is True
    assert Bestellung.objects.get(bedarf="Normal").prio is False
    b = Bestellung.objects.get(bedarf="Normal")
    assert client_fuer(konten[L]).post(f"/bestellungen/{b.pk}/", {"prio": ["false", "true"]}).status_code == 403
    b.refresh_from_db()
    assert b.prio is False


# --- „bestellt“ füllt Datum und Person ---

def test_status_bestellt_fuellt_leere_felder(konten):
    from django.utils import timezone

    from kern.models import Protokolleintrag

    b = Bestellung.objects.create(bedarf="Kleber")
    c = client_fuer(konten[M])
    # Die Zeile schickt alle Felder mit, auch die leeren
    c.post(f"/bestellungen/{b.pk}/", {"status": "bestellt", "bestellt_am": "", "bestellt_von": ""},
           HTTP_HX_REQUEST="true")
    b.refresh_from_db()
    assert b.bestellt_am == timezone.localdate() and b.bestellt_von == konten[M].person
    daten = Protokolleintrag.objects.get(objekt_typ="bestellung", objekt_id=b.pk, aktion="geaendert").daten
    assert daten["bestellt_von"][1]["id"] == konten[M].person.pk and daten["bestellt_am"][1] == timezone.localdate().isoformat()


def test_status_bestellt_ueberschreibt_nichts_und_nur_beim_wechsel(konten):
    b = Bestellung.objects.create(bedarf="Schrauben", bestellt_am="2026-10-01", bestellt_von=konten[P].person)
    client_fuer(konten[M]).post(f"/bestellungen/{b.pk}/", {"status": "bestellt"}, HTTP_HX_REQUEST="true")
    b.refresh_from_db()
    assert b.bestellt_am.isoformat() == "2026-10-01" and b.bestellt_von == konten[P].person

    # Andere Änderungen (auch „Bestellt am“ von Hand) füllen nichts und ändern den Status nicht
    b = Bestellung.objects.create(bedarf="Dübel")
    client_fuer(konten[M]).post(f"/bestellungen/{b.pk}/", {"bestellt_am": "2026-10-02"}, HTTP_HX_REQUEST="true")
    b.refresh_from_db()
    assert b.status == "offen" and b.bestellt_von is None
    # Status bleibt „bestellt“, Person wird später geleert → kein erneutes Füllen
    b = Bestellung.objects.create(bedarf="Nägel", status="bestellt")
    client_fuer(konten[M]).post(f"/bestellungen/{b.pk}/", {"projekt": "X"}, HTTP_HX_REQUEST="true")
    b.refresh_from_db()
    assert b.bestellt_von is None and b.bestellt_am is None
    # Zurück auf „offen“ lässt Datum und Person stehen
    b = Bestellung.objects.create(bedarf="Leim", status="bestellt", bestellt_am="2026-10-03", bestellt_von=konten[M].person)
    client_fuer(konten[M]).post(f"/bestellungen/{b.pk}/", {"status": "offen"}, HTTP_HX_REQUEST="true")
    b.refresh_from_db()
    assert b.bestellt_am.isoformat() == "2026-10-03" and b.bestellt_von == konten[M].person


def test_neue_zeile_gleich_bestellt_und_systemkonto_nicht_eingetragen(konten):
    from django.utils import timezone

    client_fuer(konten[M]).post("/bestellungen/neu/", {"neu-bedarf": "Sofort", "neu-aufnahmedatum": "2026-11-03",
                                                     "neu-status": "bestellt"})
    b = Bestellung.objects.get(bedarf="Sofort")
    assert b.bestellt_von == konten[M].person and b.bestellt_am == timezone.localdate()

    system = konten[A]
    system.systemkonto = True
    system.save()
    b = Bestellung.objects.create(bedarf="Toner")
    client_fuer(system).post(f"/bestellungen/{b.pk}/", {"status": "bestellt"}, HTTP_HX_REQUEST="true")
    b.refresh_from_db()
    assert b.bestellt_von is None and b.bestellt_am == timezone.localdate()


def test_lesend_kann_nicht_bestellt_setzen(konten):
    b = Bestellung.objects.create(bedarf="Kabel")
    assert client_fuer(konten[L]).post(f"/bestellungen/{b.pk}/", {"status": "bestellt"}).status_code == 403
    b.refresh_from_db()
    assert b.status == "offen" and b.bestellt_von is None


# --- Liefertermin ---

def test_liefertermin_setzen_leeren_und_markierung(konten):
    from datetime import date, timedelta

    from kern.models import Protokolleintrag

    gestern = date.today() - timedelta(days=1)
    b = Bestellung.objects.create(bedarf="Motor")
    c = client_fuer(konten[M])
    c.post(f"/bestellungen/{b.pk}/", {"liefertermin": gestern.isoformat()}, HTTP_HX_REQUEST="true")
    b.refresh_from_db()
    assert b.liefertermin == gestern
    assert Protokolleintrag.objects.get(objekt_typ="bestellung", objekt_id=b.pk).daten["liefertermin"] == [None, gestern.isoformat()]
    seite = c.get("/bestellungen/").content.decode()
    assert f'id="b{b.pk}-liefertermin"' in seite and "bestelltermin--ueberfaellig" in seite
    for status in ("erhalten",):
        b.status = status
        b.save()
        assert "bestelltermin--ueberfaellig" not in c.get("/bestellungen/").content.decode()
    b.status = "bestellt"
    b.liefertermin = date.today()  # heute ist noch nicht überschritten
    b.save()
    assert "bestelltermin--ueberfaellig" not in c.get("/bestellungen/").content.decode()
    c.post(f"/bestellungen/{b.pk}/", {"liefertermin": ""}, HTTP_HX_REQUEST="true")
    b.refresh_from_db()
    assert b.liefertermin is None
    assert client_fuer(konten[L]).post(f"/bestellungen/{b.pk}/", {"liefertermin": "2026-01-01"}).status_code == 403


def test_warnung_einmal_an_besteller_und_nach_verschieben_erneut(konten, settings):
    from datetime import date

    from bestellungen.warnungen import liefertermine_pruefen
    from zusammenarbeit.models import Benachrichtigung, MailStatus

    settings.EMAIL_HOST = "smtp.example.test"
    besteller = konten[P]
    besteller.mail_einstellungen = {"liefertermin": True}
    besteller.save()
    b = Bestellung.objects.create(bedarf="Sonde", status="bestellt", liefertermin=date(2026, 11, 2),
                                  bestellt_von=besteller.person, eingetragen_von=konten[M].person)
    Bestellung.objects.create(bedarf="Fertig", status="erhalten", liefertermin=date(2026, 11, 1),
                              bestellt_von=besteller.person)
    Bestellung.objects.create(bedarf="Heute fällig", liefertermin=date(2026, 11, 3), bestellt_von=besteller.person)

    assert liefertermine_pruefen(date(2026, 11, 2)) == 0  # am Liefertermin selbst noch nicht
    assert liefertermine_pruefen(date(2026, 11, 3)) == 1
    assert liefertermine_pruefen(date(2026, 11, 3)) == 0  # nur einmal
    assert liefertermine_pruefen(date(2026, 11, 4)) == 1  # „Heute fällig“ vom 3.11.
    warnungen = Benachrichtigung.objects.filter(art="liefertermin").order_by("id")
    assert [w.empfaenger for w in warnungen] == [besteller.person, besteller.person]
    assert "Sonde" in warnungen[0].text and "02.11.2026" in warnungen[0].text
    assert warnungen[0].mail_status == MailStatus.OFFEN  # Ereignis eingeschaltet

    b.liefertermin = date(2026, 11, 10)
    b.save()
    assert liefertermine_pruefen(date(2026, 11, 10)) == 0
    assert liefertermine_pruefen(date(2026, 11, 11)) == 1


def test_warnung_ohne_besteller_an_eingetragen_von_ohne_mail(konten):
    from datetime import date

    from bestellungen.warnungen import liefertermine_pruefen
    from kern.models import Person
    from zusammenarbeit.models import Benachrichtigung, MailStatus

    platzhalter = Person.objects.create(anzeigename="Platzhalter 01", bereich=konten[M].person.bereich)
    Bestellung.objects.create(bedarf="Ventil", liefertermin=date(2026, 11, 1), bestellt_von=platzhalter,
                              eingetragen_von=konten[M].person)
    Bestellung.objects.create(bedarf="Niemand", liefertermin=date(2026, 11, 1))
    assert liefertermine_pruefen(date(2026, 11, 3)) == 1
    w = Benachrichtigung.objects.get(art="liefertermin")
    assert w.empfaenger == konten[M].person and w.mail_status == MailStatus.KEINE  # E-Mail Standard aus
    assert not Bestellung.objects.filter(warnung_fuer_termin__isnull=True).exists()
    # Öffnen führt zur Bestellliste
    antwort = client_fuer(konten[M]).get(f"/posteingang/{w.pk}/")
    assert antwort.status_code == 302 and antwort["Location"] == "/bestellungen/"


def test_liefertermin_mail_mit_link(konten, settings, mailoutbox):
    from datetime import date

    from bestellungen.warnungen import liefertermine_pruefen
    from zusammenarbeit.mail import offene_versenden

    settings.EMAIL_HOST = "smtp.example.test"
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    konten[M].mail_einstellungen = {"liefertermin": True}
    konten[M].save()
    Bestellung.objects.create(bedarf="Rohr", liefertermin=date(2026, 11, 1), bestellt_von=konten[M].person)
    liefertermine_pruefen(date(2026, 11, 2))
    assert offene_versenden() == 1
    assert "Rohr" in mailoutbox[0].subject and "/bestellungen/" in mailoutbox[0].body


# --- Lieferant-Vorschläge ---

def test_lieferanten_vorschlaege_alphabetisch_und_zusammengefasst(konten):
    from bestellungen.views import lieferanten

    for name in ["Conrad", "conrad", "Conrad", "  Baumarkt  Nord ", "", "Ärztebedarf", "zubehör", "Zubehör"]:
        Bestellung.objects.create(bedarf="x", lieferant=name)
    # häufigste Schreibweise gewinnt, bei Gleichstand die mit großem Anfangsbuchstaben
    assert lieferanten(Bestellung.objects.order_by("id")) == ["Ärztebedarf", "Baumarkt Nord", "Conrad", "Zubehör"]
    seite = client_fuer(konten[L]).get("/bestellungen/").content.decode()
    assert '<datalist id="lieferanten-vorschlaege"><option value="Ärztebedarf">' in seite
