"""Seitenleiste der Projektliste: Aufgabendetail neben der Liste, Antworten tauschen beide aus."""

from django.shortcuts import render

from kern.hilfen import als_zahl

from .ansicht import aufgabe_laden, block_laden, detail_seite_kontext, zeilen_kontext, zeilen_laden


def offene_seitenleiste(request):
    """Aufgabe, die in der Seitenleiste offen ist, aus der die Anfrage kommt; None von allen anderen Seiten."""
    return als_zahl(request.POST.get("seitenleiste")) if request.htmx else None


def liste_oob(konto, projekt, zeilen=(), block=None, weg=None):
    """Was die Antwort aus der Seitenleiste in der Liste mit austauscht; ausgeblendete Zeilen stören nicht."""
    return {
        "oob_zeilen": zeilen_laden([z for z in zeilen if z and z != block]),
        "oob_block": block_laden(block) if block else None,
        "oob_weg": weg, **zeilen_kontext(konto, projekt),
    }


def seitenleiste_antwort(request, offen, zeilen=(), block=None):
    """Antwort auf eine Aktion in der Seitenleiste, statt der Weiterleitung auf die Detailseite: ihr neuer
    Inhalt, dazu out of band die betroffenen Zeilen oder ein ganzer Block der Liste."""
    aufgabe = aufgabe_laden(offen)
    return render(request, "projekte/_seitenleiste_antwort.html", {
        **liste_oob(request.user, aufgabe.projekt, zeilen, block), **detail_seite_kontext(request, aufgabe),
    })
