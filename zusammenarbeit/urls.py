from django.urls import path

from . import views

urlpatterns = [
    path("aufgaben/<int:pk>/kommentare/", views.kommentar_anlegen, name="kommentar_anlegen"),
    path("kommentare/<int:pk>/loeschen/", views.kommentar_loeschen, name="kommentar_loeschen"),
    path("aufgaben/<int:pk>/anhaenge/", views.anhang_hochladen, name="anhang_hochladen"),
    path("anhaenge/<int:pk>/", views.anhang_herunterladen, name="anhang"),
    path("anhaenge/<int:pk>/loeschen/", views.anhang_loeschen, name="anhang_loeschen"),
    path("posteingang/", views.posteingang, name="posteingang"),
    path("posteingang/feld/", views.posteingang_feld, name="posteingang_feld"),
    path("posteingang/zahl/", views.posteingang_zahl, name="posteingang_zahl"),
    path("posteingang/<int:pk>/", views.benachrichtigung_oeffnen, name="benachrichtigung_oeffnen"),
]
