from django.urls import path

from . import api, live, views

urlpatterns = [
    path("", views.teamplaner, name="teamplaner"),
    path("kalender/", views.teamplaner, {"lesen": True}, name="kalender"),
    # Teamplaner-Ansichten im Einstellungsbereich
    path("einstellungen/ansichten/teamplaner/neu/", views.ansicht_bearbeiten, name="ansicht_neu"),
    path("einstellungen/ansichten/teamplaner/<int:pk>/", views.ansicht_bearbeiten, name="ansicht_bearbeiten"),
    path("einstellungen/ansichten/teamplaner/<int:pk>/loeschen/", views.ansicht_loeschen, name="ansicht_loeschen"),
    path("api/planung/ansichten", api.ansichten, name="api-ansichten"),
    path("api/planung/raster", api.raster_daten, name="api-raster"),
    path("api/planung/palette", api.palette, name="api-palette"),
    path("api/planung/einteilungen", api.einteilung_anlegen, name="api-einteilung-anlegen"),
    path("api/planung/einteilungen/<int:pk>", api.einteilung, name="api-einteilung"),
    path("api/planung/abwesenheiten", api.abwesenheit_anlegen, name="api-abwesenheit-anlegen"),
    path("api/planung/abwesenheiten/<int:pk>", api.abwesenheit, name="api-abwesenheit"),
    path("api/planung/tagesinfo/<str:datum>", api.tagesinfo, name="api-tagesinfo"),
    path("api/planung/tagesfreigabe/<str:datum>", api.tagesfreigabe, name="api-tagesfreigabe"),
    path("api/planung/stream", live.stream, name="api-stream"),
]
