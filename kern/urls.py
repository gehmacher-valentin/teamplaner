from django.urls import path

from . import views

urlpatterns = [
    path("gesund/", views.gesund, name="gesund"),
    path("konto/foto/", views.konto_foto, name="konto_foto"),
    path("personen/<int:pk>/foto/", views.person_foto, name="person_foto"),
    path("personen/vorschlaege/", views.personen_vorschlaege, name="personen_vorschlaege"),
    path("sitzung/frist/", views.sitzung_frist, name="sitzung_frist"),
]
