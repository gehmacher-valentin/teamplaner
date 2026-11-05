from django.urls import path

from . import api, views

urlpatterns = [
    path("gantt/", views.gantt, name="gantt"),
    # Gantt-Ansichten im Einstellungsbereich
    path("einstellungen/ansichten/gantt/neu/", views.ansicht_bearbeiten, name="gantt_ansicht_neu"),
    path("einstellungen/ansichten/gantt/<int:pk>/", views.ansicht_bearbeiten, name="gantt_ansicht_bearbeiten"),
    path("einstellungen/ansichten/gantt/<int:pk>/loeschen/", views.ansicht_loeschen, name="gantt_ansicht_loeschen"),
    path("api/gantt/ansichten", api.ansichten, name="api-gantt-ansichten"),
    path("api/gantt/einstellungen", api.einstellungen, name="api-gantt-einstellungen"),
    path("api/gantt/<int:pk>", api.daten, name="api-gantt-daten"),
    path("api/gantt/<int:pk>/aufgaben/<int:aufgabe_id>", api.aufgabe, name="api-gantt-aufgabe"),
    path("api/gantt/<int:pk>/projekte/<int:projekt_id>", api.projekt, name="api-gantt-projekt"),
    path("api/gantt/<int:pk>/projekte/<int:projekt_id>/zuordnung", api.ansicht_projekt, name="api-gantt-zuordnung"),
    path("api/gantt/<int:pk>/abhaengigkeiten", api.abhaengigkeit_anlegen, name="api-gantt-abh-anlegen"),
    path("api/gantt/<int:pk>/abhaengigkeiten/<int:abh_id>", api.abhaengigkeit, name="api-gantt-abh"),
]
