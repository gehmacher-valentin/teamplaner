from django.urls import path

from . import views

urlpatterns = [
    path("meine-aufgaben/", views.meine_aufgaben, name="meine_aufgaben"),
    path("suche/", views.suche, name="suche"),
    path("suche/vorschlaege/", views.suche_vorschlaege, name="suche_vorschlaege"),
    path("projekte/", views.projekte, name="projekte"),
    path("projekte/neu/", views.projekt_anlegen, name="projekt_anlegen"),
    path("projekte/<int:pk>/", views.projekt, name="projekt"),
    path("projekte/<int:pk>/prioritaet/", views.projekt_prioritaet, name="projekt_prioritaet"),
    path("projekte/<int:pk>/bearbeiten/", views.projekt_bearbeiten, name="projekt_bearbeiten"),
    path("projekte/<int:pk>/abschnitte/", views.abschnitt_anlegen, name="abschnitt_anlegen"),
    path("projekte/<int:pk>/abschnitte/sortieren/", views.abschnitte_sortieren, name="abschnitte_sortieren"),
    path("abschnitte/<int:pk>/", views.abschnitt_bearbeiten, name="abschnitt_bearbeiten"),
    path("projekte/<int:pk>/aufgaben/", views.aufgabe_anlegen, name="aufgabe_anlegen_ohne_abschnitt"),
    path("projekte/<int:pk>/abschnitte/<int:abschnitt_id>/aufgaben/", views.aufgabe_anlegen, name="aufgabe_anlegen"),
    path("projekte/<int:pk>/aufgaben/verschieben/", views.aufgabe_verschieben, name="aufgabe_verschieben"),
    path("aufgaben/<int:pk>/", views.aufgabe, name="aufgabe"),
    path("aufgaben/<int:pk>/feld/", views.aufgabe_feld, name="aufgabe_feld"),
    path("aufgaben/<int:pk>/erledigt/", views.aufgabe_erledigt, name="aufgabe_erledigt"),
    path("aufgaben/<int:pk>/loeschen/", views.aufgabe_loeschen, name="aufgabe_loeschen"),
    path("aufgaben/<int:pk>/unteraufgaben/", views.unteraufgabe_anlegen, name="unteraufgabe_anlegen"),
]
