"""Unteraufgaben als vollwertige Aufgaben mit Hauptaufgabe: anlegen, Rechte, bis zu drei Ebenen,
Detailseite, Abhaken mit „alle mit erledigen“, Abschnitt, Löschen und Liste."""

import pytest

from kern.models import Protokolleintrag, Rolle
from projekte.models import Abschnitt, Aufgabe, Status
from zusammenarbeit.models import Kommentar

from .conftest import MI

pytestmark = pytest.mark.django_db

A, BL, P, M, L = Rolle.ADMIN, Rolle.BEREICHSLEITUNG, Rolle.PLANER, Rolle.MITARBEITER, Rolle.LESEND


def anlegen(client, haupt, titel="Platten zuschneiden", **extra):
    return client.post(f"/aufgaben/{haupt.pk}/unteraufgaben/", {"titel": titel, **extra})


def unter(haupt, titel, erledigt=False):
    status = Status.standard_erledigt() if erledigt else Status.standard_offen()
    return Aufgabe.objects.create(projekt=haupt.projekt, abschnitt=haupt.abschnitt, eltern=haupt, titel=titel, status=status)


def test_anlegen_ist_vollwertige_aufgabe(client_fuer, konten, aufgabe):
    person = konten[M].person
    antwort = anlegen(client_fuer(konten[P]), aufgabe, verantwortlich=person.pk, faellig_am=MI.isoformat())
    assert antwort.status_code == 302
    u = Aufgabe.objects.get(eltern=aufgabe)
    assert (u.projekt, u.abschnitt, u.verantwortlich, u.faellig_am) == (aufgabe.projekt, aufgabe.abschnitt, person, MI)
    assert not u.status.ist_erledigt
    # Im Verlauf der Hauptaufgabe sichtbar
    assert Protokolleintrag.objects.filter(objekt_typ="unteraufgabe", aktion="angelegt", aufgabe_id=aufgabe.pk).exists()


@pytest.mark.parametrize("rolle, status", [(A, 302), (BL, 302), (P, 302), (M, 403), (L, 403)])
def test_anlegen_rechte(client_fuer, konten, aufgabe, rolle, status):
    assert anlegen(client_fuer(konten[rolle]), aufgabe).status_code == status
    assert Aufgabe.objects.filter(eltern=aufgabe).count() == (1 if status == 302 else 0)


def test_hoechstens_drei_ebenen(client_fuer, konten, aufgabe):
    c = client_fuer(konten[A])
    eltern = aufgabe
    for titel in ["Unterkonstruktion", "Gestell", "Füße"]:
        anlegen(c, eltern, titel)
        eltern = Aufgabe.objects.get(eltern=eltern)
    assert (eltern.titel, eltern.tiefe) == ("Füße", 3)
    anlegen(c, eltern, "Zu tief")
    assert not Aufgabe.objects.filter(eltern=eltern).exists()
    # Pfad im Aufgabendetail, kein Formular für eine vierte Ebene
    seite = c.get(f"/aufgaben/{eltern.pk}/").content.decode()
    assert all(t in seite for t in ["Hallenboden Nord", "Unterkonstruktion", "Gestell"])
    assert f'action="/aufgaben/{eltern.pk}/unteraufgaben/"' not in seite


def test_detailseite_und_kommentar(client_fuer, konten, aufgabe):
    u = unter(aufgabe, "Gefälle einstellen")
    c = client_fuer(konten[P])
    seite = c.get(f"/aufgaben/{u.pk}/").content.decode()
    assert "Gefälle einstellen" in seite and aufgabe.titel in seite
    assert f'action="/aufgaben/{u.pk}/unteraufgaben/"' in seite  # zweite Ebene möglich
    assert "Gefälle einstellen" in c.get(f"/aufgaben/{aufgabe.pk}/").content.decode()
    c.post(f"/aufgaben/{u.pk}/kommentare/", {"text": "Wasserwaage liegt im Lager"})
    assert Kommentar.objects.filter(aufgabe=u).count() == 1


@pytest.mark.parametrize("auswahl, erwartet", [("alle", [True, True, True]), ("keine", [False, True, False]),
                                               ("", [False, True, False])])
def test_abhaken_mit_unteraufgaben(client_fuer, konten, aufgabe, auswahl, erwartet):
    offen, schon = unter(aufgabe, "Fugen vorbereiten"), unter(aufgabe, "Platten zuschneiden", erledigt=True)
    tiefer = unter(offen, "Fugenband zuschneiden")  # zweite Ebene zählt mit
    from projekte.dienste import offene_unteraufgaben
    assert offene_unteraufgaben(aufgabe) == 2
    client_fuer(konten[M]).post(f"/aufgaben/{aufgabe.pk}/erledigt/", {"erledigt": "1", "unteraufgaben": auswahl})
    for a in (aufgabe, offen, schon, tiefer):
        a.refresh_from_db()
    assert aufgabe.status.ist_erledigt
    assert [offen.status.ist_erledigt, schon.status.ist_erledigt, tiefer.status.ist_erledigt] == erwartet


def test_wieder_oeffnen_laesst_unteraufgaben(client_fuer, konten, aufgabe):
    u = unter(aufgabe, "Platten zuschneiden", erledigt=True)
    aufgabe.status = Status.standard_erledigt()
    aufgabe.save()
    client_fuer(konten[M]).post(f"/aufgaben/{aufgabe.pk}/erledigt/", {"erledigt": "0", "unteraufgaben": "alle"})
    u.refresh_from_db()
    assert u.status.ist_erledigt


def test_abhaken_der_unteraufgabe_im_verlauf_der_hauptaufgabe(client_fuer, konten, aufgabe):
    u = unter(aufgabe, "Gefälle einstellen")
    client_fuer(konten[M]).post(f"/aufgaben/{u.pk}/erledigt/", {"erledigt": "1"})
    assert Protokolleintrag.objects.filter(objekt_typ="unteraufgabe", aktion="erledigt", aufgabe_id=aufgabe.pk).exists()


def test_abschnitt_folgt_der_hauptaufgabe(client_fuer, konten, aufgabe, projekt):
    u = unter(aufgabe, "Unterkonstruktion")
    tiefer = unter(u, "Gestell")
    neu = Abschnitt.objects.create(projekt=projekt, name="Abschluss", sortierung=99)
    c = client_fuer(konten[P])
    antwort = c.post(f"/projekte/{projekt.pk}/aufgaben/verschieben/", {"id": aufgabe.pk, "abschnitt": neu.pk}, format="json")
    assert antwort.status_code == 204
    u.refresh_from_db()
    tiefer.refresh_from_db()
    assert u.abschnitt == neu and tiefer.abschnitt == neu
    # Über das Feld auf der Detailseite zurück in den alten Abschnitt: alle Ebenen folgen
    alt = aufgabe.abschnitt_id
    aufgabe.refresh_from_db()
    c.post(f"/aufgaben/{aufgabe.pk}/feld/", {"ansicht": "detail", "feld": "abschnitt", "wert": alt,
                                             "version": aufgabe.version}, HTTP_HX_REQUEST="true")
    tiefer.refresh_from_db()
    assert tiefer.abschnitt_id == alt


def test_loeschen(client_fuer, konten, aufgabe, projekt):
    u1, u2 = unter(aufgabe, "Platten zuschneiden"), unter(aufgabe, "Fugen vorbereiten")
    tiefer = unter(u2, "Fugenband")
    c = client_fuer(konten[P])
    antwort = c.post(f"/aufgaben/{u1.pk}/loeschen/")
    assert antwort["Location"] == f"/aufgaben/{aufgabe.pk}/"
    c.post(f"/aufgaben/{aufgabe.pk}/loeschen/")
    assert not Aufgabe.objects.filter(pk__in=[aufgabe.pk, u2.pk, tiefer.pk]).exists()


def test_projektliste_zeigt_unteraufgaben_unter_der_hauptaufgabe(client_fuer, konten, aufgabe, projekt):
    gefaelle = unter(aufgabe, "Gefälle einstellen")
    unter(aufgabe, "Platten zuschneiden", erledigt=True)
    unter(gefaelle, "Keile setzen")
    seite = client_fuer(konten[L]).get(f"/projekte/{projekt.pk}/?status=alle").content.decode()
    block = seite.index(f'id="aufgabe-block-{aufgabe.pk}"')
    assert "1 / 2" in seite
    assert block < seite.index("aufgabe-zeile--unter") < seite.index("Gefälle einstellen") < seite.index("Keile setzen")
    # verschachtelt: der Block der Unteraufgabe liegt in der Unterliste der Hauptaufgabe
    assert seite.index(f'data-eltern="{aufgabe.pk}"') < seite.index(f'id="aufgabe-block-{gefaelle.pk}"')
