from django.urls import path

from . import views

urlpatterns = [
    path("notizen/", views.uebersicht, name="notizen"),
    path("notizen/ordner/<int:pk>/", views.uebersicht, name="notizordner"),
    path("notizen/ordner/neu/", views.ordner_bearbeiten, name="notizordner_neu"),
    path("notizen/ordner/<int:pk>/bearbeiten/", views.ordner_bearbeiten, name="notizordner_bearbeiten"),
    path("notizen/ordner/<int:pk>/loeschen/", views.ordner_loeschen, name="notizordner_loeschen"),
    path("notizen/neu/", views.notiz_neu, name="notiz_neu"),
    path("notizen/speichern/", views.notiz_speichern, name="notiz_speichern"),
    path("notizen/<int:pk>/", views.notiz, name="notiz"),
    path("notizen/<int:pk>/loeschen/", views.notiz_loeschen, name="notiz_loeschen"),
    path("notizen/<int:pk>/anhaenge/", views.anhang_hochladen, name="notiz_anhang_hochladen"),
    path("notizen/anhaenge/<int:pk>/", views.anhang_herunterladen, name="notiz_anhang"),
    path("notizen/anhaenge/<int:pk>/loeschen/", views.anhang_loeschen, name="notiz_anhang_loeschen"),
]
